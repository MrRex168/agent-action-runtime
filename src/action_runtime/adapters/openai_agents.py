from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from ..action import Action
from ..executor import execute


def _receipt_json(receipt: Any) -> str:
    payload = asdict(receipt)
    payload["status"] = receipt.status.value
    if receipt.approval is not None:
        payload["approval"]["decision"] = receipt.approval.decision.value
    return json.dumps(payload, default=str)


def as_openai_tool(
    action: Action[..., Any],
    *,
    description: str,
) -> Any:
    """Expose an Agent Action Runtime action as an OpenAI Agents SDK FunctionTool.

    The OpenAI Agents SDK is an optional dependency. Importing the core package
    never requires it.
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

    async def invoke(**kwargs: Any) -> str:
        receipt = await execute(action, **kwargs)
        return _receipt_json(receipt)

    invoke.__name__ = action.name
    invoke.__doc__ = description
    invoke.__annotations__ = {
        key: value
        for key, value in getattr(action.func, "__annotations__", {}).items()
        if key != "return"
    }
    invoke.__annotations__["return"] = str

    return function_tool(
        invoke,
        name_override=action.name,
        description_override=description,
    )
