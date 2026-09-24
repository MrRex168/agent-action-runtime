from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any

from .action import Action, Permission
from .models import ExecutionReceipt, ExecutionStatus


async def _invoke(action: Action[..., Any], *args: Any, **kwargs: Any) -> Any:
    if inspect.iscoroutinefunction(action.func):
        awaitable = action(*args, **kwargs)
        if action.config.timeout is None:
            return await awaitable
        return await asyncio.wait_for(awaitable, timeout=action.config.timeout)

    # A Python worker thread cannot be safely terminated after a timeout.
    # Refuse the configuration rather than report failure while a side-effecting
    # action may still be running in the background.
    if action.config.timeout is not None:
        raise RuntimeError(
            "timeouts require an async action; sync actions cannot be safely interrupted"
        )

    return action(*args, **kwargs)


async def execute(action: Action[..., Any], *args: Any, **kwargs: Any) -> ExecutionReceipt:
    started = time.perf_counter()

    if action.config.permission is Permission.DENY:
        return ExecutionReceipt(
            action=action.name,
            status=ExecutionStatus.DENIED,
            attempts=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            error="Action denied by policy",
        )

    if action.config.permission is Permission.ASK:
        return ExecutionReceipt(
            action=action.name,
            status=ExecutionStatus.APPROVAL_REQUIRED,
            attempts=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            error="Action requires approval",
        )

    if action.config.timeout is not None and not inspect.iscoroutinefunction(action.func):
        return ExecutionReceipt(
            action=action.name,
            status=ExecutionStatus.FAILED,
            attempts=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            error=(
                "RuntimeError: timeouts require an async action; "
                "sync actions cannot be safely interrupted"
            ),
        )

    max_attempts = action.config.retries + 1
    last_error: str | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            value = await _invoke(action, *args, **kwargs)
        except asyncio.TimeoutError:
            last_error = f"TimeoutError: action exceeded {action.config.timeout}s timeout"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            return ExecutionReceipt(
                action=action.name,
                status=ExecutionStatus.SUCCESS,
                attempts=attempt,
                duration_ms=(time.perf_counter() - started) * 1000,
                result=value,
            )

    return ExecutionReceipt(
        action=action.name,
        status=ExecutionStatus.FAILED,
        attempts=max_attempts,
        duration_ms=(time.perf_counter() - started) * 1000,
        error=last_error,
    )
