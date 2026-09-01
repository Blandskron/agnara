"""Protocol-neutral outcomes for capability execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import field
from enum import StrEnum
from types import MappingProxyType

from agnara._frozen import frozen_slots_dataclass

__all__ = ["CanonicalResult", "Failure", "FailureCode", "Success"]


class FailureCode(StrEnum):
    """Stable semantic failure categories shared by every transport."""

    INVALID_INPUT = "invalid_input"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    INTERACTION_REQUIRED = "interaction_required"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    INTERNAL_FAILURE = "internal_failure"


type FailureDetail = bool | int | float | str | tuple[FailureDetail, ...] | None


@frozen_slots_dataclass
class Success[T]:
    """A successfully produced capability value."""

    value: T


@frozen_slots_dataclass
class Failure:
    """A safe semantic failure that adapters can project to their protocols.

    ``details`` is copied into a read-only mapping. Detail values are limited
    to immutable scalar values and tuples so canonical outcomes can be shared
    without locks or defensive copies.
    """

    code: FailureCode
    message: str
    details: Mapping[str, FailureDetail] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, FailureCode):
            raise TypeError(f"code must be a FailureCode, got {type(self.code).__name__}")
        if not isinstance(self.message, str) or not self.message:
            raise TypeError("message must be a non-empty string")
        if not isinstance(self.details, Mapping):
            raise TypeError("details must be a mapping")

        copied: dict[str, FailureDetail] = {}
        for key, value in self.details.items():
            if not isinstance(key, str):
                raise TypeError("failure detail keys must be strings")
            if not _is_detail(value):
                raise TypeError("failure detail values must be immutable scalars or nested tuples")
            copied[key] = value
        object.__setattr__(self, "details", MappingProxyType(copied))


type CanonicalResult[T] = Success[T] | Failure


def _is_detail(value: object) -> bool:
    if value is None or isinstance(value, str | bool | int | float):
        return True
    return isinstance(value, tuple) and all(_is_detail(item) for item in value)
