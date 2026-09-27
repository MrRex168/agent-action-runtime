"""OpenAI Agents SDK -> Agent Action Runtime execution-boundary demo.

Requires:
    pip install -e ".[openai]"
    export OPENAI_API_KEY=...

Execution boundary:

    OpenAI Agents SDK
            |
            v
    agent selects update_crm
            |
            v
    Agent Action Runtime
            |
            v
    Policy -> Execute -> Verify -> Recover -> Receipt
            |
            v
       actual CRM state

The model decides which action to call. Agent Action Runtime controls how the
selected action executes and whether its outcome can be trusted.

This demo intentionally simulates a misleading CRM API: the API reports 200,
but the requested state change never becomes true.
"""

import asyncio

from agents import Agent, Runner

from action_runtime import action
from action_runtime.adapters.openai_agents import as_openai_tool

crm = {"1842": {"status": "new"}}


def verify_qualified(result: dict) -> bool:
    return crm[result["customer_id"]]["status"] == "qualified"


@action(verify=verify_qualified, on_failure="escalate")
def update_crm(customer_id: str, status: str) -> dict:
    # The API claims success, but deliberately does not mutate crm.
    return {
        "customer_id": customer_id,
        "requested_status": status,
        "api_status": 200,
    }


tool = as_openai_tool(
    update_crm,
    description="Update a customer's CRM status.",
)

agent = Agent(
    name="CRM Agent",
    instructions=(
        "Use the CRM tool when asked to update a customer. "
        "The tool returns an Agent Action Runtime execution receipt. "
        "Report its status, verification result, and recovery accurately. "
        "Never claim the CRM update succeeded when the receipt status is needs_review."
    ),
    tools=[tool],
)


async def main() -> None:
    print("OPENAI AGENTS SDK")
    print('Requested:      customer "1842" -> "qualified"')
    print("Agent selects:  update_crm")
    print()
    print("ACTION RUNTIME BOUNDARY")
    print("Policy -> Execute -> Verify -> Recover -> Receipt")
    print()

    result = await Runner.run(
        agent,
        'Update customer "1842" to "qualified".',
    )

    print("AGENT RECEIVES RUNTIME RECEIPT")
    print(result.final_output)
    print()
    print("ACTUAL STATE")
    print("Requested:      qualified")
    print("CRM state:      ", crm["1842"]["status"])
    print()
    print("BOUNDARY RESULT")
    print("API returned 200, but the intended CRM state did not change.")
    print("Agent Action Runtime verification prevents that tool call from being trusted as success.")

    assert crm["1842"]["status"] == "new"


if __name__ == "__main__":
    asyncio.run(main())
