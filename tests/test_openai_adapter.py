import asyncio
import json
import sys
import types

import pytest

from action_runtime import action, execute
from action_runtime.adapters.openai_agents import as_openai_tool


def test_openai_adapter_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "agents", None)

    @action()
    def ping() -> str:
        return "pong"

    with pytest.raises(ImportError, match=r"\[openai\]"):
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
    assert receipt == {
        "action": "update",
        "status": "needs_review",
        "attempts": 1,
        "verified": False,
        "recovery": "escalate",
        "error_code": "verification_failed",
    }
    assert "1842" not in output


def test_openai_adapter_rejects_ask_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_agents = types.ModuleType("agents")
    fake_agents.function_tool = lambda func, **kwargs: func
    monkeypatch.setitem(sys.modules, "agents", fake_agents)

    @action(permission="ask")
    def send_email() -> None:
        pass

    with pytest.raises(ValueError, match="approval flow"):
        as_openai_tool(send_email, description="Send email.")


@pytest.fixture
def wrap_tool(monkeypatch: pytest.MonkeyPatch):
    fake_agents = types.ModuleType("agents")
    fake_agents.function_tool = lambda func, **kwargs: func
    monkeypatch.setitem(sys.modules, "agents", fake_agents)
    return as_openai_tool


@pytest.mark.asyncio
async def test_tool_success_returns_only_safe_metadata(wrap_tool) -> None:
    @action()
    def customer() -> dict:
        return {"token": "private-customer-token"}

    tool = wrap_tool(customer, description="Look up customer.")
    output = await tool()

    assert json.loads(output) == {
        "action": "customer",
        "status": "success",
        "attempts": 1,
        "verified": None,
        "recovery": None,
        "error_code": None,
    }
    assert "private-customer-token" not in output
    assert (await execute(customer)).result == {"token": "private-customer-token"}


@pytest.mark.asyncio
async def test_tool_failure_hides_exception_and_skips_projection(wrap_tool) -> None:
    @action()
    def update() -> None:
        raise RuntimeError("private-connection-string")

    def project(result):
        pytest.fail("Projection should run only on success")

    tool = wrap_tool(update, description="Update customer.", result_projection=project)
    output = await tool()

    assert json.loads(output) == {
        "action": "update",
        "status": "needs_review",
        "attempts": 1,
        "verified": None,
        "recovery": "escalate",
        "error_code": "outcome_uncertain",
    }
    assert "private-connection-string" not in output
    trusted_receipt = await execute(update)
    assert trusted_receipt.error == "RuntimeError: private-connection-string"
    assert trusted_receipt.history[0].error == trusted_receipt.error


@pytest.mark.asyncio
async def test_tool_never_traverses_unsupported_results_by_default(wrap_tool) -> None:
    class Unsupported:
        def __deepcopy__(self, memo):
            pytest.fail("Default serialization copied a result")

        def __str__(self):
            pytest.fail("Default serialization stringified a result")

    @action()
    def fetch() -> Unsupported:
        return Unsupported()

    tool = wrap_tool(fetch, description="Fetch result.")
    receipt = json.loads(await tool())

    assert receipt["status"] == "success"
    assert receipt["attempts"] == 1
    assert "result" not in receipt


@pytest.mark.asyncio
async def test_tool_exposes_only_explicit_projection(wrap_tool) -> None:
    @action()
    def fetch() -> dict:
        return {"count": 3, "token": "private-customer-token"}

    tool = wrap_tool(
        fetch, description="Fetch result.",
        result_projection=lambda result: {"count": result["count"]},
    )
    output = await tool()

    assert json.loads(output)["result"] == {"count": 3}
    assert "private-customer-token" not in output


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [object(), float("nan"), "🧪" * 400, ["item"] * 2000])
async def test_tool_omits_oversized_or_invalid_projection(wrap_tool, value) -> None:
    @action()
    def fetch() -> object:
        return value

    tool = wrap_tool(fetch, description="Fetch result.", result_projection=lambda result: result)
    output = await tool()
    receipt = json.loads(output)

    assert len(output.encode("utf-8")) <= 4096
    assert receipt["status"] == "success"
    assert receipt["error_code"] is None
    assert "result" not in receipt


@pytest.mark.asyncio
async def test_tool_handles_projection_exceptions(wrap_tool) -> None:
    @action()
    def fetch() -> None:
        return None

    def project(result):
        raise ValueError("private-projection-detail")

    tool = wrap_tool(fetch, description="Fetch result.", result_projection=project)
    output = await tool()

    assert json.loads(output)["status"] == "success"
    assert "result" not in json.loads(output)
    assert "private-projection-detail" not in output
