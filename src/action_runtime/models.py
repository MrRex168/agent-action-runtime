from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"
    NEEDS_REVIEW = "needs_review"


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class Approval:
    decision: ApprovalDecision
    by: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Attempt:
    number: int
    executed: bool
    verified: bool | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    action: str
    status: ExecutionStatus
    attempts: int
    duration_ms: float
    result: Any = None
    verified: bool | None = None
    recovery: str | None = None
    approval: Approval | None = None
    error: str | None = None
    history: tuple[Attempt, ...] = ()
