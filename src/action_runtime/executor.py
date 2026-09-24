from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any

from .action import Action, Permission, Recovery
from .models import Attempt, ExecutionReceipt, ExecutionStatus


async def _invoke(action: Action[..., Any], *args: Any, **kwargs: Any) -> Any:
    if inspect.iscoroutinefunction(action.func):
        awaitable = action(*args, **kwargs)
        if action.config.timeout is None:
            return await awaitable
        return await asyncio.wait_for(awaitable, timeout=action.config.timeout)

    if action.config.timeout is not None:
        raise RuntimeError(
            "timeouts require an async action; sync actions cannot be safely interrupted"
        )

    return action(*args, **kwargs)


async def _verify(action: Action[..., Any], value: Any) -> bool:
    verifier = action.config.verify
    if verifier is None:
        return True

    outcome = verifier(value)
    if inspect.isawaitable(outcome):
        outcome = await outcome
    return bool(outcome)


def _terminal_failure(
    action: Action[..., Any],
    *,
    started: float,
    attempts: int,
    history: list[Attempt],
    error: str,
    result: Any = None,
    verified: bool | None = None,
) -> ExecutionReceipt:
    recovery = action.config.on_failure
    status = (
        ExecutionStatus.NEEDS_REVIEW
        if recovery is Recovery.ESCALATE
        else ExecutionStatus.FAILED
    )
    return ExecutionReceipt(
        action=action.name,
        status=status,
        attempts=attempts,
        duration_ms=(time.perf_counter() - started) * 1000,
        result=result,
        verified=verified,
        recovery=recovery.value,
        error=error,
        history=tuple(history),
    )


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
            recovery=Recovery.FAIL.value,
            error=(
                "RuntimeError: timeouts require an async action; "
                "sync actions cannot be safely interrupted"
            ),
        )

    history: list[Attempt] = []
    max_attempts = (
        action.config.retries + 1
        if action.config.on_failure is Recovery.RETRY
        else 1
    )

    for attempt in range(1, max_attempts + 1):
        try:
            value = await _invoke(action, *args, **kwargs)
        except asyncio.TimeoutError:
            error = f"TimeoutError: action exceeded {action.config.timeout}s timeout"
            history.append(Attempt(number=attempt, executed=True, error=error))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            history.append(Attempt(number=attempt, executed=True, error=error))
        else:
            try:
                verified = await _verify(action, value)
            except Exception as exc:
                error = f"VerificationError: {type(exc).__name__}: {exc}"
                history.append(
                    Attempt(number=attempt, executed=True, verified=False, error=error)
                )
            else:
                if verified:
                    history.append(Attempt(number=attempt, executed=True, verified=True))
                    return ExecutionReceipt(
                        action=action.name,
                        status=ExecutionStatus.SUCCESS,
                        attempts=attempt,
                        duration_ms=(time.perf_counter() - started) * 1000,
                        result=value,
                        verified=True if action.config.verify is not None else None,
                        history=tuple(history),
                    )

                error = "VerificationError: verifier returned false"
                history.append(
                    Attempt(number=attempt, executed=True, verified=False, error=error)
                )

        if action.config.on_failure is not Recovery.RETRY:
            return _terminal_failure(
                action,
                started=started,
                attempts=attempt,
                history=history,
                error=error,
                result=value if "value" in locals() else None,
                verified=False if error.startswith("VerificationError:") else None,
            )

    return _terminal_failure(
        action,
        started=started,
        attempts=max_attempts,
        history=history,
        error=error,
        result=value if "value" in locals() else None,
        verified=False if error.startswith("VerificationError:") else None,
    )
