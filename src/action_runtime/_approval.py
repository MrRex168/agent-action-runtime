"""Internal encoding for approval-bound calls."""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any, Callable


def _check_json_value(value: Any) -> None:
    if type(value) in (type(None), bool, int, float, str):
        return
    if type(value) is list:
        for item in value:
            _check_json_value(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("Approval argument dictionaries require string keys")
            _check_json_value(item)
        return
    raise ValueError("Approval arguments require plain JSON values")


def encode_call(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> bytes:
    bound = inspect.signature(func).bind(*args, **kwargs)
    bound.apply_defaults()
    call = [list(bound.args), bound.kwargs]
    _check_json_value(call)
    # Mapping order is observable by Python code, so it is part of the binding.
    return json.dumps(call, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def argument_digest(call: bytes) -> str:
    return hashlib.sha256(call).hexdigest()
