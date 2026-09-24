import pytest

from action_runtime import Action, ExecutionStatus, action, execute


def test_action_decorator_creates_action() -> None:
    @action()
    def greet(name: str) -> str:
        return f"Hello, {name}"

    assert isinstance(greet, Action)
    assert greet.name == "greet"
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
async def test_execute_failure_returns_failed_receipt() -> None:
    @action()
    def explode() -> None:
        raise RuntimeError("boom")

    receipt = await execute(explode)

    assert receipt.status is ExecutionStatus.FAILED
    assert receipt.attempts == 1
    assert receipt.result is None
    assert receipt.error == "RuntimeError: boom"
