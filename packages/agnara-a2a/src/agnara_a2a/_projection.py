"""Numeric domain and JSON shape across the protobuf ``Value`` binding (ADR 0098 D3/D4)."""

from __future__ import annotations

import math
from typing import Any

#: The integer range a protobuf double carries exactly.
SAFE_INTEGER = 2**53 - 1

#: Defensive recursion bound. The binding refuses earlier (ADR 0098 D7:
#: 47 input and 31 output levels with protobuf 7.36.2), so this only stops a
#: pathological value before Python's own recursion limit does.
MAX_DEPTH = 64


class UnrepresentableValue(Exception):
    """A value is outside the profile's numeric or shape domain."""


def normalize_input(value: Any, depth: int = 0) -> Any:
    """Turn protobuf ``Value`` floats back into JSON-shaped capability input.

    Integral floats within ``±(2**53 - 1)`` become ``int``; larger integral
    values may already have been rounded and are refused. Everything else
    passes unchanged, and the compiled input contract stays authoritative.
    """
    if depth > MAX_DEPTH:
        raise UnrepresentableValue
    if value is None or type(value) in (bool, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise UnrepresentableValue
        if value.is_integer():
            if abs(value) > SAFE_INTEGER:
                raise UnrepresentableValue
            return int(value)
        return value
    if type(value) is int:
        if abs(value) > SAFE_INTEGER:
            raise UnrepresentableValue
        return value
    if type(value) is dict:
        return {key: normalize_input(item, depth + 1) for key, item in value.items()}
    if type(value) is list:
        return [normalize_input(item, depth + 1) for item in value]
    raise UnrepresentableValue


def project_output(value: Any, depth: int = 0) -> Any:
    """Keep explicit JSON built-ins the binding carries faithfully; tuples become arrays."""
    if depth > MAX_DEPTH:
        raise UnrepresentableValue
    if value is None or type(value) in (bool, str):
        return value
    if type(value) is int:
        if abs(value) > SAFE_INTEGER:
            raise UnrepresentableValue
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise UnrepresentableValue
        return value
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise UnrepresentableValue
        return {key: project_output(item, depth + 1) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [project_output(item, depth + 1) for item in value]
    raise UnrepresentableValue
