"""The immutable declaration of one capability.

A ``CapabilityDefinition`` is what the rest of the runtime compiles from.
It is frozen so that the registry can be frozen after startup compilation
and shared across threads without locking, which PRINCIPLES.md P6 requires
under free-threaded CPython.

Nothing here knows about HTTP, MCP, A2A, events, tasks or CLIs. A
capability is not intrinsically a route or a tool; those are exposures
attached later by adapters (ADR 0002, ADR 0003).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import field
from enum import StrEnum
from typing import Any

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.identity import CapabilityId
from agnara.capability.metadata import Confirmation, Idempotency, Risk
from agnara.errors import DefinitionError

__all__ = ["CapabilityDefinition"]

#: The handler's call semantics -- sync versus async, streaming, task
#: handles -- are deliberately not decided here. EPIC 4 owns execution;
#: this type only records what was declared.
Handler = Callable[..., Any]


def _coerce_effects(effects: Iterable[str]) -> frozenset[str]:
    if isinstance(effects, str):
        raise DefinitionError(
            "effects must be a collection of strings, not the single string "
            f"{effects!r}; pass {{{effects!r}}} to declare one effect"
        )
    try:
        collected = frozenset(effects)
    except TypeError as exc:
        # Not iterable, or holds something unhashable. Either way the
        # caller gets Agnara's error rather than a raw TypeError.
        raise DefinitionError(f"effects must be an iterable of strings: {exc}") from exc
    for effect in collected:
        if not isinstance(effect, str):
            raise DefinitionError(f"effect {effect!r} is not a string")
        if not effect.strip():
            raise DefinitionError("an effect must not be empty or whitespace")
    return collected


def _coerce[EnumT: StrEnum](value: object, enum: type[EnumT], field_name: str) -> EnumT:
    """Resolve ``value`` to a member of ``enum``, accepting its string form.

    Members are compared rather than passed to ``enum(value)`` so that an
    invalid value produces Agnara's own error listing the allowed values,
    instead of a bare `ValueError` from the standard library.
    """
    for member in enum:
        if value == member.value:
            return member
    allowed = ", ".join(repr(member.value) for member in enum)
    raise DefinitionError(f"invalid {field_name} {value!r}: expected one of {allowed}")


@frozen_slots_dataclass
class CapabilityDefinition:
    """One declared, protocol-neutral application capability.

    Construction validates eagerly and raises `DefinitionError`, so a
    malformed declaration fails at import or startup rather than on the
    first invocation (ADR 0005).

    The metadata fields describe what invoking this capability does. They
    feed policy engines and agent discovery, and they are never
    authorization on their own (ADR 0008).
    """

    id: CapabilityId
    handler: Handler
    description: str | None = None
    effects: frozenset[str] = field(default_factory=frozenset)
    risk: Risk = Risk.LOW
    confirmation: Confirmation = Confirmation.NEVER
    #: Defaults to ``UNKNOWN``: a capability is not idempotent merely
    #: because nobody said otherwise (RFC 0001).
    idempotency: Idempotency = Idempotency.UNKNOWN

    def __post_init__(self) -> None:
        if not isinstance(self.id, CapabilityId):
            raise DefinitionError(
                f"id must be a CapabilityId, got {type(self.id).__name__}; "
                "use CapabilityId.parse() to build one from a string"
            )
        if not callable(self.handler):
            raise DefinitionError(
                f"handler for {self.id} must be callable, got {type(self.handler).__name__}"
            )
        # Copy into a frozenset so a set the caller still holds cannot
        # mutate this definition after construction.
        object.__setattr__(self, "effects", _coerce_effects(self.effects))
        object.__setattr__(self, "risk", _coerce(self.risk, Risk, "risk"))
        object.__setattr__(
            self, "confirmation", _coerce(self.confirmation, Confirmation, "confirmation")
        )
        object.__setattr__(
            self, "idempotency", _coerce(self.idempotency, Idempotency, "idempotency")
        )

    def has_effect(self, effect: str) -> bool:
        """Whether this capability declares ``effect``."""
        return effect in self.effects

    def __str__(self) -> str:
        return str(self.id)
