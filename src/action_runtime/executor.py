from __future__ import annotations

import inspect
import time
from typing import Any

from .action import Action
from .models import ExecutionReceipt, ExecutionStatus


async def execute(action: Action[..., Any], *args: Any, **kwargs: Any) -> ExecutionReceipt:
    started = time.perf_counter()

    try:
        value = action(*args, **kwargs)
        if inspect.isawaitable(value):
            value = await value
    except Exception as exc:
        return ExecutionReceipt(
            action=action.name,
            status=ExecutionStatus.FAILED,
            attempts=1,
            duration_ms=(time.perf_counter() - started) * 1000,
            error=f"{type(exc).__name__}: {exc}",
        )

    return ExecutionReceipt(
        action=action.name,
        status=ExecutionStatus.SUCCESS,
        attempts=1,
        duration_ms=(time.perf_counter() - started) * 1000,
        result=value,
    )
