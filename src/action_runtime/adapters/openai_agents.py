from __future__ import annotations

import inspect
import json
from typing import Any, Callable

from ..action import Action
from ..executor import execute
from ..models import ExecutionReceipt, ExecutionStatus


_MAX_RECEIPT_BYTES = 4096
_MAX_ACTION_CHARS = 128
_JSON_ENCODER = json.JSONEncoder(ensure_ascii=True, allow_nan=False, separators=(",", ":"))

_ERROR_CODES = {
    ExecutionStatus.SUCCESS: None,
    ExecutionStatus.FAILED: "execution_failed",
    ExecutionStatus.DENIED: "denied",
    ExecutionStatus.APPROVAL_REQUIRED: "approval_required",
    ExecutionStatus.NEEDS_REVIEW: "outcome_uncertain",
}


def _receipt_json(
    receipt: ExecutionReceipt,
    result_projection: Callable[[Any], Any] | None,
) -> str:
    error_code = _ERROR_CODES[receipt.status]
    if receipt.status in (ExecutionStatus.FAILED, ExecutionStatus.NEEDS_REVIEW):
        if receipt.verified is False:
            error_code = "verification_failed"

    metadata = _JSON_ENCODER.encode({
        "action": receipt.action[:_MAX_ACTION_CHARS],
        "status": receipt.status.value,
        "attempts": receipt.attempts,
        "verified": receipt.verified,
        "recovery": receipt.recovery,
        "error_code": error_code,
    })
    if receipt.status is not ExecutionStatus.SUCCESS or result_projection is None:
        return metadata

    prefix = metadata[:-1] + ',"result":'
    remaining = _MAX_RECEIPT_BYTES - len(prefix) - len("}")
    projected_chunks = []
    try:
        for chunk in _JSON_ENCODER.iterencode(result_projection(receipt.result)):
            # ASCII-only serialization makes character and byte counts identical.
            remaining -= len(chunk)
            if remaining < 0:
                return metadata
            projected_chunks.append(chunk)
    except Exception:
        # Projection is optional. Its failure cannot replace the execution outcome.
        return metadata

    return prefix + "".join(projected_chunks) + "}"


def as_openai_tool(
    action: Action[..., Any],
    *,
    description: str,
    result_projection: Callable[[Any], Any] | None = None,
) -> Any:
    """Expose an Agent Action Runtime action as an OpenAI Agents SDK FunctionTool.

    The OpenAI Agents SDK is an optional dependency. Importing the core package
    never requires it. The optional result projection selects model-visible
    JSON data from a successful result, subject to the receipt size limit.
    """
    try:
        from agents import function_tool
    except ImportError as exc:
        raise ImportError(
            'OpenAI adapter requires: pip install "agent-action-runtime[openai]"'
        ) from exc

    if action.config.permission.value == "ask":
        raise ValueError(
            "permission='ask' actions should use the runtime approval flow directly; "
            "automatic model tool calls cannot supply human approval"
        )

    async def invoke(*args: Any, **kwargs: Any) -> str:
        receipt = await execute(action, *args, **kwargs)
        return _receipt_json(receipt, result_projection)

    invoke.__name__ = action.name
    invoke.__doc__ = description
    invoke.__annotations__ = {
        key: value
        for key, value in getattr(action.func, "__annotations__", {}).items()
        if key != "return"
    }
    invoke.__annotations__["return"] = str
    # The Agents SDK builds a strict tool schema from inspect.signature().
    # Preserve the action's explicit parameters while keeping the adapter's
    # model-visible return value as a serialized execution receipt.
    invoke.__signature__ = inspect.signature(action.func).replace(  # type: ignore[attr-defined]
        return_annotation=str
    )

    return function_tool(
        invoke,
        name_override=action.name,
        description_override=description,
    )
