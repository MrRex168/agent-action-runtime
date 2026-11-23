from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any

from .action import Action, Permission, Recovery
from .models import Approval, ApprovalDecision, Attempt, ExecutionReceipt, ExecutionStatus


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


async def _verify(action: Action[..., Any], value: Any) -> bool | None:
    verifier = action.config.verify
    if verifier is None:
        return None
    outcome = verifier(value)
    if inspect.isawaitable(outcome):
        outcome = await outcome
    return bool(outcome)


def _terminal_failure(action: Action[..., Any], *, started: float,
                      history: list[Attempt], approval: Approval | None,
                      result: Any) -> ExecutionReceipt:
    recovery = action.config.on_failure
    status = ExecutionStatus.NEEDS_REVIEW if recovery is Recovery.ESCALATE else ExecutionStatus.FAILED
    final_attempt = history[-1]
    return ExecutionReceipt(
        action=action.name, status=status, attempts=final_attempt.number,
        duration_ms=(time.perf_counter() - started) * 1000,
        result=result, verified=final_attempt.verified, recovery=recovery.value,
        approval=approval, error=final_attempt.error, history=tuple(history),
    )


async def execute(
    action: Action[..., Any],
    *args: Any,
    approval: Approval | ApprovalDecision | str | None = None,
    **kwargs: Any,
) -> ExecutionReceipt:
    started = time.perf_counter()
    resolved_approval: Approval | None = None
    if approval is not None:
        resolved_approval = approval if isinstance(approval, Approval) else Approval(ApprovalDecision(approval))

    if action.config.permission is Permission.DENY:
        return ExecutionReceipt(
            action=action.name, status=ExecutionStatus.DENIED, attempts=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            approval=resolved_approval, error="Action denied by policy",
        )

    if action.config.permission is Permission.ASK:
        if resolved_approval is None:
            return ExecutionReceipt(
                action=action.name, status=ExecutionStatus.APPROVAL_REQUIRED, attempts=0,
                duration_ms=(time.perf_counter() - started) * 1000,
                error="Action requires approval",
            )
        if resolved_approval.decision is ApprovalDecision.DENY:
            return ExecutionReceipt(
                action=action.name, status=ExecutionStatus.DENIED, attempts=0,
                duration_ms=(time.perf_counter() - started) * 1000,
                approval=resolved_approval, error="Action denied by approver",
            )
    elif resolved_approval is not None:
        return ExecutionReceipt(
            action=action.name, status=ExecutionStatus.FAILED, attempts=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            approval=resolved_approval,
            error="Approval can only be supplied for actions with permission='ask'",
        )

    if action.config.timeout is not None and not inspect.iscoroutinefunction(action.func):
        return ExecutionReceipt(
            action=action.name, status=ExecutionStatus.FAILED, attempts=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            recovery=Recovery.FAIL.value, approval=resolved_approval,
            error="RuntimeError: timeouts require an async action; sync actions cannot be safely interrupted",
        )

    history: list[Attempt] = []
    max_attempts = action.config.retries + 1 if action.config.on_failure is Recovery.RETRY else 1
    for attempt in range(1, max_attempts + 1):
        value: Any = None
        verified: bool | None = None
        error: str | None = None
        try:
            value = await _invoke(action, *args, **kwargs)
        except asyncio.TimeoutError:
            error = f"TimeoutError: action exceeded {action.config.timeout}s timeout"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        else:
            try:
                verified = await _verify(action, value)
            except Exception as exc:
                verified = False
                error = f"VerificationError: {type(exc).__name__}: {exc}"
            else:
                if verified is False:
                    error = "VerificationError: verifier returned false"

        history.append(Attempt(number=attempt, executed=True, verified=verified, error=error))
        if error is None:
            return ExecutionReceipt(
                action=action.name, status=ExecutionStatus.SUCCESS, attempts=attempt,
                duration_ms=(time.perf_counter() - started) * 1000,
                result=value, verified=verified,
                approval=resolved_approval, history=tuple(history),
            )

    return _terminal_failure(
        action, started=started, history=history,
        approval=resolved_approval, result=value,
    )
