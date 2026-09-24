"""Killer demo: a CRM action that executes but fails verification.

Run locally without an LLM:
    python examples/crm_failure_demo.py
"""

import asyncio

from action_runtime import ExecutionStatus, action, execute

crm = {"1842": {"status": "new"}}


def verify_qualified(result: dict) -> bool:
    return crm[result["customer_id"]]["status"] == "qualified"


@action(
    retries=1,
    verify=verify_qualified,
    on_failure="escalate",
)
def update_crm(customer_id: str, status: str) -> dict:
    # Simulate a misleading API: HTTP/API layer reports success, but the write
    # never became true in the system of record.
    return {"customer_id": customer_id, "requested_status": status, "api_status": 200}


async def main() -> None:
    receipt = await execute(update_crm, "1842", "qualified")

    print("ACTION:       ", receipt.action)
    print("ATTEMPTS:     ", receipt.attempts)
    print("VERIFIED:     ", receipt.verified)
    print("RECOVERY:     ", receipt.recovery)
    print("FINAL STATUS: ", receipt.status.value)

    assert receipt.status is ExecutionStatus.NEEDS_REVIEW


if __name__ == "__main__":
    asyncio.run(main())
