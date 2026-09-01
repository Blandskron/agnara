"""Reliable frozen, slotted value types for the core.

CPython 3.14's generated ``__setattr__`` and ``__delattr__`` for a
``dataclass(frozen=True, slots=True)`` can raise a confusing ``TypeError``
for names that are not dataclass fields. The slots transformation rebuilds
the class while the generated methods retain the pre-transformation class in
their closure.

This internal decorator keeps the standard dataclass construction and slots,
then replaces only those two guards with deterministic ``FrozenInstanceError``
failures. Generated ``__init__`` and explicit ``__post_init__`` normalization
continue to use ``object.__setattr__`` and are unaffected.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from typing import Never, dataclass_transform

__all__: list[str] = []


def _reject_assignment(self: object, name: str, value: object) -> Never:
    raise FrozenInstanceError(f"cannot assign to field {name!r}")


def _reject_deletion(self: object, name: str) -> Never:
    raise FrozenInstanceError(f"cannot delete field {name!r}")


@dataclass_transform(frozen_default=True)
def frozen_slots_dataclass[T](cls: type[T], /) -> type[T]:
    """Create a frozen slotted dataclass with clear mutation failures."""
    value_type = dataclass(frozen=True, slots=True)(cls)
    type.__setattr__(value_type, "__setattr__", _reject_assignment)
    type.__setattr__(value_type, "__delattr__", _reject_deletion)
    return value_type
