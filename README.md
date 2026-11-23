# Agent Action Runtime

> **Agents decide. Action Runtime executes safely.**

**Framework-neutral execution control for AI agent actions: permissions, approvals, retries, verification, recovery, and receipts.**

A tool returning `200 OK` does not mean the real-world action succeeded. Agent Action Runtime sits between an agent's decision and the side effect, then checks what actually happened.

```text
Agent / LLM
    |
    v
Action Runtime
    |
    +--> Policy --> Approval --> Execute --> Verify --> Recover --> Receipt
    |
    v
Tool / API / Environment
```

## The 30-second example

```python
import asyncio

from action_runtime import action, execute

crm = {"1842": {"status": "new"}}

def actually_qualified(result: dict) -> bool:
    return crm[result["customer_id"]]["status"] == "qualified"

@action(
    permission="allow",
    verify=actually_qualified,
    on_failure="escalate",
)
async def update_crm(customer_id: str, status: str) -> dict:
    return {"customer_id": customer_id, "requested_status": status}

async def main() -> None:
    receipt = await execute(update_crm, "1842", "qualified")
    print(receipt.status)    # needs_review
    print(receipt.verified)  # False
    print(receipt.history)   # execution + verification record

asyncio.run(main())
```

The agent decides **what** to do. The runtime controls **how the action executes** and whether success is trustworthy.

## Why this exists

Production agents increasingly send email, update CRMs, modify files, call APIs, create tickets, run commands, and trigger workflows. The dangerous gap is after the model chooses a tool:

- Should this action be allowed?
- Does a human need to approve it?
- What happens on timeout or transient failure?
- Did the requested state actually change?
- Should failure retry, stop, or escalate?
- What record explains what happened?

Those concerns usually end up scattered across tool functions, callbacks, prompts, and framework-specific middleware. Agent Action Runtime gives them one portable action contract.

## What you get

| Capability | V0.1 behavior |
| --- | --- |
| Policy | `allow`, `deny`, `ask` |
| Human approval | Invocation-bound approval checked by a trusted application validator |
| Retries | Bounded retries for actions explicitly declared retry-safe |
| Timeouts | Per-attempt timeout for async action calls |
| Verification | Sync or async postcondition verifier |
| Recovery | `retry`, `fail`, `escalate` |
| Receipts | Result, status, attempts, verification, recovery, approval, history |
| Frameworks | Native Python + optional OpenAI Agents SDK adapter |
| Infrastructure | Local-first, stateless, no server/database required |

> **Timeout safety:** Async timeouts request cancellation locally. A remote write may already have committed. The runtime rejects a sync action configured with a timeout before invoking it.

## Install

Until the first PyPI publish:

```bash
python -m pip install "git+https://github.com/MrRex168/agent-action-runtime.git"
```

For development:

```bash
git clone https://github.com/MrRex168/agent-action-runtime.git
cd agent-action-runtime
python -m pip install -e ".[dev]"
pytest
```

Requires Python 3.10+.

## Killer demo: API success != action success

Run without an LLM or API key:

```bash
python examples/crm_failure_demo.py
```

The fake CRM reports API success but never changes the system of record. The runtime verifies the postcondition and escalates immediately because this action uses `on_failure="escalate"`:

```text
ACTION:        update_crm
ATTEMPTS:      1
VERIFIED:      False
RECOVERY:      escalate
FINAL STATUS:  needs_review
```

**A successful tool call is not necessarily a successful action.**

## Permissions and human approval

```python
from action_runtime import action, execute

@action(permission="ask", approval_validator=approval_store.validate_and_consume)
async def send_email(to: str, body: str) -> dict:
    ...

to, body = "customer@example.com", "Hello"
request = send_email.approval_request(to, body)

# Application code presents this exact request to an authenticated reviewer.
# An authorized approval is issued and recorded by the application.
approval = await approval_service.review_and_issue(request, to=to, body=body)

receipt = await execute(send_email, to, body, approval=approval)
```

`approval_store` and `approval_service` represent trusted application code. Issue an `Approval` with `ApprovalDecision.APPROVE`, the original `ApprovalRequest`, and a finite `expires_at` in Unix seconds. The request contains a unique invocation ID, an action-instance ID, and a digest of the bound arguments. Store an immutable record of the arguments shown to the reviewer along with the request, and preserve dictionary order when reconstructing those arguments.

The runtime checks the decision, expiry, action instance, and argument digest before calling the configured sync or async validator. The validator must authenticate the full record against a trusted issuance source, enforce the reviewer's authority and expiry, and return literal `True` only after authorization. For single-use approval, the store must check and consume the record in one atomic operation so concurrent requests cannot both pass. Treat approval records as sensitive and reissue a consumed approval only through a new review. An invocation ID or digest alone carries no authorization.

Approval-bound arguments accept plain JSON values with string dictionary keys and finite numbers. The runtime binds default values and equivalent positional and keyword arguments, preserves dictionary order, and supplies fresh snapshots to attempts and reconciliation. Approvals apply to the registered action instance that created the request. Recreating the action, including on process restart, requires a new request. A successful admission covers that execution and its configured safe retries.

Existing `ask` callers must migrate from bare approvals and string shorthand to bound records and a configured validator. Missing approval returns `approval_required`, invalid approval returns `denied`, and explicit denial remains terminal. Only a validated approval is attached to a receipt. Direct calls to `ask` and `deny` actions raise `PermissionError`. Keep the raw callable and action registration under trusted application control.

## Verification and recovery

A verifier checks the postcondition after the tool returns. An exception, timeout, or failed verification can leave a remote write's outcome uncertain.

**Retry default:** `retries=N` sets the retry budget. To authorize replay, also set `retry_safe=True` and use `on_failure="retry"`. Declare retry safety when repeating the action is harmless or the downstream service enforces deduplication for the same logical operation. An unresolved failure without that declaration returns `needs_review` after one attempt, including under `on_failure="fail"`. For retry-safe actions, `fail` stops after one attempt and `escalate` reports `needs_review`. Exhausting an authorized retry budget reports `failed`, which describes runtime execution and does not establish that a remote write was absent.

An application can pass its idempotency key as an ordinary action argument. The runtime reuses the invocation arguments across attempts. Choose a unique key for each logical operation and reuse it for that operation while the downstream service's deduplication guarantee applies. For agent tools, use trusted application state to supply the key when replay safety depends on it. The runtime does not generate keys, enforce downstream deduplication, or guarantee exactly-once delivery.

```python
async def already_written(record: dict, *, idempotency_key: str) -> bool:
    return await store.confirm_write(record, idempotency_key=idempotency_key)

@action(
    retries=2,
    retry_safe=True,  # store.write enforces deduplication by key
    verify=lambda result: result["persisted"] is True,
    reconcile=already_written,
)
async def write_record(record: dict, *, idempotency_key: str) -> dict:
    return await store.write(record, idempotency_key=idempotency_key)

receipt = await execute(write_record, record, idempotency_key=operation_id)
```

The optional `reconcile` callback receives the original action arguments after a failed invocation or verification, before any replay. It can be synchronous or asynchronous. Use a read-only check against an authoritative source and return `True` only when it confirms the intended operation succeeded. A false result or callback exception leaves success unconfirmed and does not authorize replay. A confirmed operation returns `success` with `verified=True` and no result payload. Attempt history retains the original error and records the reconciliation outcome and any callback error.

## OpenAI Agents SDK

The core package has no OpenAI dependency.

```bash
python -m pip install "agent-action-runtime[openai] @ git+https://github.com/MrRex168/agent-action-runtime.git"
```

```python
from action_runtime import action
from action_runtime.adapters.openai_agents import as_openai_tool

@action(retries=2, verify=verify_result, on_failure="escalate")
def update_crm(customer_id: str, status: str) -> dict:
    ...

tool = as_openai_tool(
    update_crm,
    description="Update a customer's CRM status.",
)
```

**OpenAI Agents SDK decides which tool to call. Agent Action Runtime controls how the selected action executes and whether its outcome can be trusted.**

The adapter keeps those responsibilities separate:

```text
OpenAI Agents SDK -> agent selects action -> Agent Action Runtime
                                            |
                                            +-> Policy -> Execute -> Verify -> Recover -> Receipt
                                                                          |
                                                                          v
                                                                    actual state
```

The agent receives the structured runtime receipt instead of bypassing policy, verification, and recovery. Agent Action Runtime is an execution-control layer underneath the selected action, not a replacement for the agent SDK or a workflow orchestrator.

See `examples/openai_agents_demo.py` for the CRM scenario where the API returns `200` but the requested state never changes.

## Execution receipt

```python
ExecutionReceipt(
    action="update_crm",
    status=ExecutionStatus.NEEDS_REVIEW,
    attempts=1,
    verified=False,
    recovery="escalate",
    error="VerificationError: verifier returned false",
    history=(...),
)
```

Receipts are designed to make action outcomes inspectable by the calling agent, application, logs, or future hosted control plane.

## What this is not

Agent Action Runtime is **not** an agent framework, LLM SDK, workflow engine, MCP gateway, observability platform, evaluation framework, memory system, credential vault, or sandbox.

It owns one boundary:

> **When an agent decides to act, how should that action execute safely and reliably?**

## V0.1 scope

```text
Action -> Policy -> Approval -> Execute -> Verify -> Recover -> Receipt
```

**Included now:** native Python actions, policy, approval, async timeouts, retries, verification, recovery, receipts, OpenAI Agents adapter.

**Not yet:** durable pending approvals, distributed execution, credential management, sandboxing, centralized policy service, dashboards, or additional framework adapters.

## Examples

- `examples/crm_failure_demo.py` — deterministic verification failure and escalation, no API key.
- `examples/openai_agents_demo.py` — OpenAI Agents SDK integration.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
python -m build
python -m twine check dist/*
```

CI tests Python 3.10, 3.11, and 3.12, validates distributions, and smoke-tests the built wheel.

See `CONTRIBUTING.md` for contribution guidance and `SECURITY.md` for vulnerability reporting.

## Roadmap

Near-term candidates after V0.1:

- More framework adapters
- Durable approval handoff
- Policy composition
- Idempotency primitives
- Structured receipt exporters
- Hosted policy/approval/audit control plane

The open-source runtime will remain focused on the execution boundary.

## License

MIT
