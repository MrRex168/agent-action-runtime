"""Contract test against the real OpenAI Agents SDK.

No API key or model call is required. This verifies that the adapter exposes
an Action Runtime action as a strict FunctionTool with the original action
parameters and can invoke the tool with SDK-parsed arguments.
"""

import json

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


@pytest.mark.asyncio
async def test_real_openai_sdk_invocation_returns_safe_receipt() -> None:
    pytest.importorskip("agents")
    from agents import RunContextWrapper
    from agents.tool_context import ToolContext
    from openai.types.responses import ResponseFunctionToolCall

    received = []

    @action()
    async def fetch_customer(customer_id: str, *, region: str) -> dict:
        received.append((customer_id, region))
        return {"customer_id": customer_id, "secret": "private-result"}

    tool = as_openai_tool(fetch_customer, description="Fetch a customer.")
    arguments = '{"customer_id":"customer-1","region":"west"}'
    tool_call = ResponseFunctionToolCall(
        type="function_call", call_id="test-call", name=tool.name, arguments=arguments,
    )
    context = ToolContext.from_agent_context(
        RunContextWrapper(context=None), tool_call_id=tool_call.call_id, tool_call=tool_call,
    )
    output = await tool.on_invoke_tool(context, arguments)

    assert received == [("customer-1", "west")]
    assert json.loads(output) == {
        "action": "fetch_customer",
        "status": "success",
        "attempts": 1,
        "verified": None,
        "recovery": None,
        "error_code": None,
    }



@pytest.mark.asyncio
async def test_sdk_fallback_hides_unexpected_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("agents")
    from agents import RunContextWrapper
    from agents.tool_context import ToolContext
    from openai.types.responses import ResponseFunctionToolCall

    async def broken_execute(*args, **kwargs):
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr("action_runtime.adapters.openai_agents.execute", broken_execute)

    @action()
    def fetch() -> None:
        pytest.fail("Unexpected runtime failure should prevent invocation")

    tool = as_openai_tool(fetch, description="Fetch customer.")
    tool_call = ResponseFunctionToolCall(
        type="function_call", call_id="test-call", name=tool.name, arguments="{}",
    )
    context = ToolContext.from_agent_context(
        RunContextWrapper(context=None), tool_call_id=tool_call.call_id, tool_call=tool_call,
    )

    output = await tool.on_invoke_tool(context, tool_call.arguments)

    assert output == "The tool could not return an execution receipt."
