from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Generic, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")
Verifier = Callable[[Any], bool | Awaitable[bool]]


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

    def __post_init__(self) -> None:
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if self.retries < 0:
            raise ValueError("retries cannot be negative")


@dataclass(frozen=True, slots=True)
class Action(Generic[P, R]):
    func: Callable[P, R] | Callable[P, Awaitable[R]]
    config: ActionConfig

    @property
    def name(self) -> str:
        return self.config.name

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Any:
        return self.func(*args, **kwargs)


def action(
    *,
    name: str | None = None,
    permission: Permission | str = Permission.ALLOW,
    timeout: float | None = None,
    retries: int = 0,
    verify: Verifier | None = None,
    on_failure: Recovery | str = Recovery.RETRY,
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
        )
        return Action(func=func, config=config)

    return decorator
