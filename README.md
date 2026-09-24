# Agent Action Runtime

> **Agents decide. Action Runtime executes safely.**

Lightweight, framework-neutral execution control for AI agent actions.

Agent Action Runtime is the layer between an agent's decision and the tool that performs the action. It is designed to make real-world agent actions explicit, controllable, and eventually verifiable without forcing developers into a new agent framework.

## Why

Agent frameworks are good at deciding what an agent should do. Developers still repeatedly implement the execution boundary themselves: permissions, timeouts, retries, verification, recovery, approvals, and execution records.

Agent Action Runtime gives those concerns one portable contract.

```text
Agent / LLM
    |
    v
Action Runtime
    |
    +--> Policy --> Execute --> Verify --> Recover --> Receipt
    |
    v
Tools / Environment
```

## Current capabilities

- A typed `@action(...)` contract
- `allow`, `deny`, and `ask` execution policies
- Explicit human approval or denial for `ask` actions
- Approval identity/reason preserved in execution receipts
- Retry budgets with explicit attempt counts
- Enforced timeouts for async actions
- Safe rejection of sync timeout configurations
- Native sync and async Python actions
- Result verification with sync or async verifier functions
- Explicit `retry`, `fail`, and `escalate` recovery strategies
- Per-attempt execution history and richer structured receipts
- Configuration validation
- Tests for the core execution contract

> **Safety note:** hard timeouts are currently supported for async actions only. Python cannot safely terminate a running worker thread, so a sync action configured with a timeout is rejected before execution rather than risking duplicate or uncontrolled side effects.

## Quick start

Install the project in development mode:

```bash
python -m pip install -e ".[dev]"
```

Create and execute an action:

```python
import asyncio

from action_runtime import action, execute


@action(permission="allow", retries=2)
def update_crm(customer_id: str, status: str) -> dict:
    return {"customer_id": customer_id, "status": status}


async def main() -> None:
    receipt = await execute(update_crm, "1842", "qualified")
    print(receipt)


asyncio.run(main())
```

The executor returns an `ExecutionReceipt` containing the action name, status, attempts, duration, result, verification state, recovery decision, error, and per-attempt history.

Verification lets the runtime distinguish **"the tool returned"** from **"the action actually succeeded"**:

```python
def verified(result: dict) -> bool:
    return result.get("status") == "qualified"

@action(
    retries=2,
    verify=verified,
    on_failure="escalate",
)
def update_crm(customer_id: str) -> dict:
    ...
```

Recovery is intentionally small in V1: `retry`, `fail`, or `escalate`. Escalated actions return `needs_review` so a caller can hand control to a human or higher-level system.

Policies are declared directly on an action:

```python
@action(permission="deny")
def delete_customer(customer_id: str) -> None:
    ...

@action(permission="ask")
async def send_email(to: str, body: str) -> None:
    ...
```

A denied action never executes. An `ask` action returns `approval_required` without executing until the caller supplies an explicit decision:

```python
from action_runtime import Approval, ApprovalDecision

pending = await execute(send_email)
assert pending.status == "approval_required"

receipt = await execute(
    send_email,
    approval=Approval(
        ApprovalDecision.APPROVE,
        by="ops@example.com",
        reason="Customer requested the message",
    ),
)
```

A denial is terminal and the tool is never called. An approval cannot override a `deny` policy. Approval metadata is preserved in the final receipt for auditability.

**V1 resume model:** the caller invokes `execute(...)` again with the same action inputs plus the approval decision. Agent Action Runtime is intentionally stateless, so it does not persist pending actions or arguments between processes.

## What this is not

Agent Action Runtime is not an agent framework, LLM SDK, workflow engine, MCP gateway, observability platform, evaluation framework, memory system, or sandbox.

It focuses on one boundary:

> **When an agent decides to act, how should that action execute safely and reliably?**

## Roadmap

The V1 execution lifecycle is:

```text
Action -> Policy -> Approval -> Execute -> Verify -> Recover -> Receipt
```

The project will add these capabilities incrementally rather than bundling a large framework around the core.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```

Requires Python 3.10+.

## License

MIT
