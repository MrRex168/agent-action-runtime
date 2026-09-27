"""Contract test against the real OpenAI Agents SDK.

No API key or model call is required. This verifies that the adapter exposes
an Action Runtime action as a strict FunctionTool with the original action
parameters instead of the adapter's internal **kwargs signature.
"""

import pytest

from action_runtime import action
from action_runtime.adapters.openai_agents import as_openai_tool


def test_real_openai_sdk_schema_preserves_action_parameters() -> None:
    pytest.importorskip("agents")

    @action()
    def update_crm(customer_id: str, status: str) -> dict:
        return {"customer_id": customer_id, "status": status}

    tool = as_openai_tool(
        update_crm,
        description="Update a customer's CRM status.",
    )

    schema = tool.params_json_schema

    assert tool.name == "update_crm"
    assert set(schema["properties"]) == {"customer_id", "status"}
    assert set(schema["required"]) == {"customer_id", "status"}
    assert schema["additionalProperties"] is False
