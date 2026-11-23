from __future__ import annotations

import asyncio
import inspect
import json
import math
import time
from typing import Any

from ._approval import argument_digest, encode_call
from .action import Action, Permission, Recovery
from .models import Approval, ApprovalDecision, ApprovalRequest, Attempt, ExecutionReceipt, ExecutionStatus


async def _invoke(action: Action[..., Any], *args: Any, **kwargs: Any) -> Any:
    if inspect.iscoroutinefunction(action.func):
        awaitable = action.func(*args, **kwargs)
        if action.config.timeout is None:
            return await awaitable
        return await asyncio.wait_for(awaitable, timeout=action.config.timeout)

    if action.config.timeout is not None:
        raise RuntimeError(
            "timeouts require an async action; sync actions cannot be safely interrupted"
        )
    return action.func(*args, **kwargs)


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
    if action.config.retry_safe is not True:
        recovery = Recovery.ESCALATE
    status = ExecutionStatus.NEEDS_REVIEW if recovery is Recovery.ESCALATE else ExecutionStatus.FAILED
    final_attempt = history[-1]
    return ExecutionReceipt(
        action=action.name, status=status, attempts=final_attempt.number,
        duration_ms=(time.perf_counter() - started) * 1000,
        result=result, verified=final_attempt.verified, recovery=recovery.value,
        approval=approval, error=final_attempt.error, history=tuple(history),
    )


async def _approved_call(
    action: Action[..., Any],
    approval: Approval,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> bytes | None:
    request = approval.request
    expires_at = approval.expires_at
    validator = action.config.approval_validator
    if (
        type(request) is not ApprovalRequest
        or type(request.invocation_id) is not str
        or not request.invocation_id
        or type(request.action_id) is not str
        or request.action_id != action._approval_action_id
        or type(request.arguments_digest) is not str
        or type(expires_at) not in (int, float)
        or (type(expires_at) is float and not math.isfinite(expires_at))
        or expires_at <= time.time()
        or (approval.by is not None and type(approval.by) is not str)
        or (approval.reason is not None and type(approval.reason) is not str)
        or validator is None
    ):
        return None

    try:
        call = encode_call(action.func, args, kwargs)
        if request.arguments_digest != argument_digest(call):
            return None
        authorized = validator(approval)
        if inspect.isawaitable(authorized):
            authorized = await authorized
    except Exception:
        return None
    if authorized is True and expires_at > time.time():
        return call
    return None


async def execute(
    action: Action[..., Any],
    *args: Any,
    approval: Approval | ApprovalDecision | str | None = None,
    **kwargs: Any,
) -> ExecutionReceipt:
    started = time.perf_counter()
    resolved_approval: Approval | None = None
    pending_approval: Approval | None = None
    approved_call: bytes | None = None

    if action.config.permission is Permission.DENY:
        return ExecutionReceipt(
            action=action.name, status=ExecutionStatus.DENIED, attempts=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            error="Action denied by policy",
        )

    if action.config.permission is Permission.ASK:
        if approval is None:
            return ExecutionReceipt(
                action=action.name, status=ExecutionStatus.APPROVAL_REQUIRED, attempts=0,
                duration_ms=(time.perf_counter() - started) * 1000,
                error="Action requires approval",
            )
        if (
            approval is ApprovalDecision.DENY
            or (type(approval) is str and approval == ApprovalDecision.DENY.value)
            or (type(approval) is Approval and approval.decision is ApprovalDecision.DENY)
        ):
            return ExecutionReceipt(
                action=action.name, status=ExecutionStatus.DENIED, attempts=0,
                duration_ms=(time.perf_counter() - started) * 1000,
                error="Action denied by approver",
            )
        if type(approval) is not Approval or approval.decision is not ApprovalDecision.APPROVE:
            return ExecutionReceipt(
                action=action.name, status=ExecutionStatus.DENIED, attempts=0,
                duration_ms=(time.perf_counter() - started) * 1000,
                error="Action requires a valid, bound approval",
            )
        pending_approval = approval
    elif approval is not None:
        return ExecutionReceipt(
            action=action.name, status=ExecutionStatus.FAILED, attempts=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            error="Approval can only be supplied for actions with permission='ask'",
        )

    if action.config.timeout is not None and not inspect.iscoroutinefunction(action.func):
        return ExecutionReceipt(
            action=action.name, status=ExecutionStatus.FAILED, attempts=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            recovery=Recovery.FAIL.value, approval=resolved_approval,
            error="RuntimeError: timeouts require an async action; sync actions cannot be safely interrupted",
        )

    if pending_approval is not None:
        approved_call = await _approved_call(action, pending_approval, args, kwargs)
        if approved_call is None:
            return ExecutionReceipt(
                action=action.name, status=ExecutionStatus.DENIED, attempts=0,
                duration_ms=(time.perf_counter() - started) * 1000,
                error="Approval is invalid, expired, or unauthorized for this invocation",
            )
        resolved_approval = pending_approval

    history: list[Attempt] = []
    max_attempts = 1
    if action.config.retry_safe is True and action.config.on_failure is Recovery.RETRY:
        max_attempts += action.config.retries
    for attempt in range(1, max_attempts + 1):
        value: Any = None
        verified: bool | None = None
        error: str | None = None
        if approved_call is not None:
            # Rebuild the approved inputs for each attempt.
            args, kwargs = json.loads(approved_call)
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

        reconciled: bool | None = None
        reconciliation_error: str | None = None
        if error is not None and action.config.reconcile is not None:
            try:
                if approved_call is not None:
                    args, kwargs = json.loads(approved_call)
                outcome = action.config.reconcile(*args, **kwargs)
                if inspect.isawaitable(outcome):
                    outcome = await outcome
                reconciled = outcome is True
            except Exception as exc:
                reconciled = False
                reconciliation_error = f"{type(exc).__name__}: {exc}"

        history.append(Attempt(
            number=attempt, executed=True, verified=verified, error=error,
            reconciled=reconciled, reconciliation_error=reconciliation_error,
        ))
        if error is None or reconciled is True:
            return ExecutionReceipt(
                action=action.name, status=ExecutionStatus.SUCCESS, attempts=attempt,
                duration_ms=(time.perf_counter() - started) * 1000,
                result=None if reconciled else value, verified=True if reconciled else verified,
                approval=resolved_approval, history=tuple(history),
            )

    return _terminal_failure(
        action, started=started, history=history,
        approval=resolved_approval, result=value,
    )
