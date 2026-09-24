"""OpenAI Agents SDK integration example.

Requires:
    pip install -e ".[openai]"
    export OPENAI_API_KEY=...

The model decides to call update_crm. Agent Action Runtime owns execution
semantics and returns a structured receipt to the agent.
"""

import asyncio

from agents import Agent, Runner

from action_runtime import action
from action_runtime.adapters.openai_agents import as_openai_tool

crm = {"1842": {"status": "new"}}


def verify_qualified(result: dict) -> bool:
    return crm[result["customer_id"]]["status"] == "qualified"


@action(retries=1, verify=verify_qualified, on_failure="escalate")
def update_crm(customer_id: str, status: str) -> dict:
    return {"customer_id": customer_id, "requested_status": status, "api_status": 200}


tool = as_openai_tool(
    update_crm,
    description="Update a customer's CRM status.",
)

agent = Agent(
    name="CRM Agent",
    instructions=(
        "Use the CRM tool when asked to update a customer. "
        "Report the runtime receipt accurately and do not claim success "
        "when status is needs_review."
    ),
    tools=[tool],
)


async def main() -> None:
    result = await Runner.run(
        agent,
        'Update customer "1842" to "qualified".',
    )
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
