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
| Human approval | Explicit approve/deny with identity + reason |
| Retries | Bounded retry budget |
| Timeouts | Hard timeout for async actions |
| Verification | Sync or async postcondition verifier |
| Recovery | `retry`, `fail`, `escalate` |
| Receipts | Result, status, attempts, verification, recovery, approval, history |
| Frameworks | Native Python + optional OpenAI Agents SDK adapter |
| Infrastructure | Local-first, stateless, no server/database required |

> **Timeout safety:** Python cannot safely terminate a running synchronous function. A sync action configured with a hard timeout is rejected before execution instead of risking duplicate or uncontrolled side effects.

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
from action_runtime import Approval, ApprovalDecision, action, execute

@action(permission="ask")
async def send_email(to: str, body: str) -> dict:
    ...

pending = await execute(send_email, "customer@example.com", "Hello")
# pending.status == approval_required

receipt = await execute(
    send_email,
    "customer@example.com",
    "Hello",
    approval=Approval(
        ApprovalDecision.APPROVE,
        by="ops@example.com",
        reason="Customer requested follow-up",
    ),
)
```

A denial is terminal. Approval cannot override `permission="deny"`. V0.1 is intentionally stateless: callers re-invoke the action with the same inputs plus the explicit approval decision.

## Verification and recovery

A verifier checks the postcondition after the tool returns:

```python
def verified(result: dict) -> bool:
    return result.get("persisted") is True

@action(
    retries=2,
    verify=verified,
    on_failure="retry",
)
async def write_record(record: dict) -> dict:
    ...
```

Recovery stays deliberately small:

- `retry`: retry within the configured budget.
- `fail`: stop after the first failed execution or verification.
- `escalate`: stop and return `needs_review`.

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

The model can choose the tool, but execution still passes through Agent Action Runtime. The agent receives the structured runtime receipt instead of bypassing policy, retry, verification, and recovery.

See `examples/openai_agents_demo.py`.

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
