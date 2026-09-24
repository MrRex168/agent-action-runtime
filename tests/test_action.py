import asyncio
import pytest

from action_runtime import Action, ExecutionStatus, Permission, action, execute


def test_action_decorator_creates_action() -> None:
    @action()
    def greet(name: str) -> str:
        return f"Hello, {name}"

    assert isinstance(greet, Action)
    assert greet.name == "greet"
    assert greet.config.permission is Permission.ALLOW
    assert greet("Ada") == "Hello, Ada"


def test_action_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="timeout"):
        @action(timeout=0)
        def invalid() -> None:
            pass

    with pytest.raises(ValueError, match="retries"):
        @action(retries=-1)
        def also_invalid() -> None:
            pass

    with pytest.raises(ValueError):
        @action(permission="unknown")
        def unknown_permission() -> None:
            pass


@pytest.mark.asyncio
async def test_execute_sync_action_returns_success_receipt() -> None:
    @action()
    def add(a: int, b: int) -> int:
        return a + b

    receipt = await execute(add, 2, 3)

    assert receipt.status is ExecutionStatus.SUCCESS
    assert receipt.result == 5
    assert receipt.attempts == 1
    assert receipt.error is None


@pytest.mark.asyncio
async def test_execute_async_action_returns_success_receipt() -> None:
    @action()
    async def greet(name: str) -> str:
        return f"Hello, {name}"

    receipt = await execute(greet, "Ada")

    assert receipt.status is ExecutionStatus.SUCCESS
    assert receipt.result == "Hello, Ada"


@pytest.mark.asyncio
async def test_denied_action_never_executes() -> None:
    called = False

    @action(permission="deny")
    def dangerous() -> None:
        nonlocal called
        called = True

    receipt = await execute(dangerous)

    assert receipt.status is ExecutionStatus.DENIED
    assert receipt.attempts == 0
    assert called is False


@pytest.mark.asyncio
async def test_ask_action_stops_before_execution() -> None:
    called = False

    @action(permission="ask")
    def send_email() -> None:
        nonlocal called
        called = True

    receipt = await execute(send_email)

    assert receipt.status is ExecutionStatus.APPROVAL_REQUIRED
    assert receipt.attempts == 0
    assert called is False


@pytest.mark.asyncio
async def test_execute_retries_then_succeeds() -> None:
    calls = 0

    @action(retries=2)
    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("temporary")
        return "ok"

    receipt = await execute(flaky)

    assert receipt.status is ExecutionStatus.SUCCESS
    assert receipt.result == "ok"
    assert receipt.attempts == 3
    assert calls == 3


@pytest.mark.asyncio
async def test_execute_stops_after_retry_budget() -> None:
    calls = 0

    @action(retries=2)
    def always_fails() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    receipt = await execute(always_fails)

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.attempts == 3
    assert calls == 3
    assert receipt.error == "RuntimeError: boom"


@pytest.mark.asyncio
async def test_async_timeout_is_retried() -> None:
    calls = 0

    @action(timeout=0.01, retries=1)
    async def slow() -> None:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)

    receipt = await execute(slow)

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.attempts == 2
    assert calls == 2
    assert receipt.error is not None
    assert receipt.error.startswith("TimeoutError:")


@pytest.mark.asyncio
async def test_sync_timeout_is_rejected_before_execution() -> None:
    called = False

    @action(timeout=0.01)
    def sync_action() -> None:
        nonlocal called
        called = True

    receipt = await execute(sync_action)

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.attempts == 0
    assert called is False
    assert receipt.error is not None
    assert "async action" in receipt.error
