import asyncio
import json
import sys
import types

import pytest

from action_runtime import action
from action_runtime.adapters.openai_agents import as_openai_tool


def test_openai_adapter_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "agents", None)

    @action()
    def ping() -> str:
        return "pong"

    with pytest.raises(ImportError, match="\[openai\]"):
        as_openai_tool(ping, description="Ping.")


def test_openai_adapter_wraps_runtime_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_function_tool(func, **kwargs):
        captured["func"] = func
        captured["kwargs"] = kwargs
        return func

    fake_agents = types.ModuleType("agents")
    fake_agents.function_tool = fake_function_tool
    monkeypatch.setitem(sys.modules, "agents", fake_agents)

    @action(verify=lambda result: result["ok"], on_failure="escalate")
    def update(customer_id: str) -> dict:
        return {"customer_id": customer_id, "ok": False}

    tool = as_openai_tool(update, description="Update CRM.")
    output = asyncio.run(tool(customer_id="1842"))
    receipt = json.loads(output)

    assert captured["kwargs"]["name_override"] == "update"
    assert receipt["status"] == "needs_review"
    assert receipt["verified"] is False


def test_openai_adapter_rejects_ask_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_agents = types.ModuleType("agents")
    fake_agents.function_tool = lambda func, **kwargs: func
    monkeypatch.setitem(sys.modules, "agents", fake_agents)

    @action(permission="ask")
    def send_email() -> None:
        pass

    with pytest.raises(ValueError, match="approval flow"):
        as_openai_tool(send_email, description="Send email.")
