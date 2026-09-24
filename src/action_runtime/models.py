from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    action: str
    status: ExecutionStatus
    attempts: int
    duration_ms: float
    result: Any = None
    error: str | None = None
