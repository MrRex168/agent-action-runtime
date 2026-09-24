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

## Milestone 1

The current foundation includes:

- A typed `@action(...)` contract
- Native sync and async Python actions
- A minimal executor
- Structured execution receipts
- Configuration validation
- Tests for the core contract

Timeout and retry settings are represented in the action contract but are intentionally not enforced yet. Runtime enforcement arrives in Milestone 2.

## Quick start

Install the project in development mode:

```bash
python -m pip install -e ".[dev]"
```

Create and execute an action:

```python
import asyncio

from action_runtime import action, execute


@action(timeout=10, retries=2)
def update_crm(customer_id: str, status: str) -> dict:
    return {"customer_id": customer_id, "status": status}


async def main() -> None:
    receipt = await execute(update_crm, "1842", "qualified")
    print(receipt)


asyncio.run(main())
```

The executor returns an `ExecutionReceipt` containing the action name, status, attempts, duration, result, and any error.

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
