from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Generic, ParamSpec, TypeVar
from uuid import uuid4

from ._approval import argument_digest, encode_call
from .models import Approval, ApprovalRequest

P = ParamSpec("P")
R = TypeVar("R")
Verifier = Callable[[Any], bool | Awaitable[bool]]
Reconciler = Callable[..., bool | Awaitable[bool]]
ApprovalValidator = Callable[[Approval], bool | Awaitable[bool]]


class Permission(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class Recovery(str, Enum):
    RETRY = "retry"
    FAIL = "fail"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class ActionConfig:
    name: str
    permission: Permission = Permission.ALLOW
    timeout: float | None = None
    retries: int = 0
    verify: Verifier | None = None
    on_failure: Recovery = Recovery.RETRY
    retry_safe: bool = False
    reconcile: Reconciler | None = None
    approval_validator: ApprovalValidator | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "permission", Permission(self.permission))
        if self.timeout is not None and (not math.isfinite(self.timeout) or self.timeout <= 0):
            raise ValueError("timeout must be finite and greater than zero")
        if self.retries < 0:
            raise ValueError("retries cannot be negative")


@dataclass(frozen=True, slots=True)
class Action(Generic[P, R]):
    func: Callable[P, R] | Callable[P, Awaitable[R]]
    config: ActionConfig
    _approval_action_id: str = field(default_factory=lambda: uuid4().hex, init=False, repr=False, compare=False)

    @property
    def name(self) -> str:
        return self.config.name

    def approval_request(self, *args: P.args, **kwargs: P.kwargs) -> ApprovalRequest:
        if self.config.permission is not Permission.ASK:
            raise ValueError("Only actions with permission='ask' require an approval request")
        call = encode_call(self.func, args, kwargs)
        return ApprovalRequest(
            invocation_id=uuid4().hex,
            action_id=self._approval_action_id,
            arguments_digest=argument_digest(call),
        )

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Any:
        if self.config.permission is not Permission.ALLOW:
            raise PermissionError("Use execute() for actions governed by approval or denial policy")
        return self.func(*args, **kwargs)


def action(
    *,
    name: str | None = None,
    permission: Permission | str = Permission.ALLOW,
    timeout: float | None = None,
    retries: int = 0,
    verify: Verifier | None = None,
    on_failure: Recovery | str = Recovery.RETRY,
    retry_safe: bool = False,
    reconcile: Reconciler | None = None,
    approval_validator: ApprovalValidator | None = None,
) -> Callable[[Callable[P, R]], Action[P, R]]:
    resolved_permission = Permission(permission)
    resolved_recovery = Recovery(on_failure)

    def decorator(func: Callable[P, R]) -> Action[P, R]:
        config = ActionConfig(
            name=name or func.__name__,
            permission=resolved_permission,
            timeout=timeout,
            retries=retries,
            verify=verify,
            on_failure=resolved_recovery,
            retry_safe=retry_safe,
            reconcile=reconcile,
            approval_validator=approval_validator,
        )
        return Action(func=func, config=config)

    return decorator
