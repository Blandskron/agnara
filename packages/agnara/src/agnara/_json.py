"""Detached, canonical JSON for values that cross into frozen core types.

Two core layers need the same guarantee: a value supplied by an adapter must
become plain, immutable, deterministic text before a frozen type holds it.
`agnara.introspection` needs it for schema fragments and exposure detail;
`agnara.exposure` needs it for the adapter-owned detail of a compiled
exposure. The depth cap and the non-finite check are security controls, so
they exist once rather than twice.

Callers supply their own error type, because a bad value is a defect in
whatever produced it and the diagnostic should name that subsystem.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Final

__all__: list[str] = []

#: Deepest JSON structure copied out of a schema fragment or exposure detail.
#: A cycle is impossible below this, and a hostile or accidental deep value
#: cannot make a later serializer recurse without bound.
MAX_DEPTH: Final = 64

#: Builds the exception a rejected value raises.
type ErrorFactory = Callable[[str], Exception]


def json_data(value: object, *, field: str, error: ErrorFactory, depth: int = 0) -> Any:
    """Detach plain JSON data, refusing anything a frozen type must not carry.

    Copying matters as much as validating: a value supplied by an adapter
    stays owned by that adapter, and a core type that shared it could change
    after it was read.
    """
    if depth > MAX_DEPTH:
        raise error(f"{field} nests deeper than {MAX_DEPTH} levels")
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise error(f"{field} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise error(f"{field} contains a non-string object key {key!r}")
            copied[key] = json_data(item, field=f"{field}.{key}", error=error, depth=depth + 1)
        return copied
    if isinstance(value, list | tuple):
        return [
            json_data(item, field=f"{field}[{index}]", error=error, depth=depth + 1)
            for index, item in enumerate(value)
        ]
    raise error(f"{field} contains a non-JSON value of type {type(value).__name__}")


def canonical_json(value: object, *, field: str, error: ErrorFactory) -> str:
    """Freeze detached JSON data into its canonical text.

    A frozen slotted dataclass cannot hold a mutable mapping and stay honest
    about immutability, and a read-only proxy would still be a view of
    something a caller could mutate. Canonical text is immutable, hashable,
    comparable and trivially deterministic to serialize.
    """
    return json.dumps(
        json_data(value, field=field, error=error),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
