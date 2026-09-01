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
from typing import Any, Self

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.identity import CapabilityId
from agnara.capability.metadata import Confirmation, Idempotency, Risk
from agnara.errors import DefinitionError
from agnara.policy.base import Policy

__all__ = ["CapabilityDefinition"]

#: The handler's call semantics -- sync versus async, streaming, task
#: handles -- are deliberately not decided here. EPIC 4 owns execution;
#: this type only records what was declared.
Handler = Callable[..., Any]


def _coerce_string_set(values: Iterable[str], field_name: str, item: str) -> frozenset[str]:
    """Copy an iterable of labels into a frozenset, validating each one.

    Copying matters: a set the caller still holds must not be able to mutate
    the definition afterwards.
    """
    if isinstance(values, str):
        raise DefinitionError(
            f"{field_name} must be a collection of strings, not the single string "
            f"{values!r}; pass {{{values!r}}} to declare one {item}"
        )
    try:
        collected = frozenset(values)
    except TypeError as exc:
        # Not iterable, or holds something unhashable. Either way the
        # caller gets Agnara's error rather than a raw TypeError.
        raise DefinitionError(f"{field_name} must be an iterable of strings: {exc}") from exc
    for value in collected:
        if not isinstance(value, str):
            raise DefinitionError(f"{item} {value!r} is not a string")
        if not value.strip():
            raise DefinitionError(f"a {item} must not be empty or whitespace")
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
    #: Permission labels a policy engine may require. Declarative only:
    #: holding a scope here grants nothing (ADR 0008, EPIC 5 enforces).
    scopes: frozenset[str] = field(default_factory=frozenset)
    risk: Risk = Risk.LOW
    confirmation: Confirmation = Confirmation.NEVER
    #: Defaults to ``UNKNOWN``: a capability is not idempotent merely
    #: because nobody said otherwise (RFC 0001).
    idempotency: Idempotency = Idempotency.UNKNOWN
    policies: tuple[Policy, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.policies, tuple):
            object.__setattr__(self, "policies", tuple(self.policies))
        for policy in self.policies:
            if not isinstance(policy, Policy):
                raise DefinitionError(f"policy {policy!r} must implement the Policy protocol")
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
        object.__setattr__(self, "effects", _coerce_string_set(self.effects, "effects", "effect"))
        object.__setattr__(self, "scopes", _coerce_string_set(self.scopes, "scopes", "scope"))
        object.__setattr__(self, "risk", _coerce(self.risk, Risk, "risk"))
        object.__setattr__(
            self, "confirmation", _coerce(self.confirmation, Confirmation, "confirmation")
        )
        object.__setattr__(
            self, "idempotency", _coerce(self.idempotency, Idempotency, "idempotency")
        )

    @classmethod
    def declare(
        cls,
        *,
        id: CapabilityId,
        handler: Handler,
        description: str | None = None,
        scopes: Iterable[str] = (),
        effects: Iterable[str] = (),
        risk: Risk | str = Risk.LOW,
        confirmation: Confirmation | str = Confirmation.NEVER,
        idempotency: Idempotency | str = Idempotency.UNKNOWN,
        policies: Iterable[Policy] = (),
    ) -> Self:
        """Build a definition from authoring-shaped arguments.

        `__init__` is annotated with the types a definition *has* once it
        exists: `effects` is a `frozenset`, `risk` is a `Risk`. Those
        annotations are correct about the attribute and wrong about the
        argument, because `__post_init__` accepts any iterable of strings and
        any enum value's string form. A dataclass has only one annotation for
        both roles, so every caller writing the documented
        ``effects={"database-write"}, risk="high"`` was a static error.

        This constructor carries the wide types, normalizes, and hands narrow
        values to `__init__`. Callers get honest typing; the attribute keeps
        its guarantee. See #24.
        """
        return cls(
            id=id,
            handler=handler,
            description=description,
            scopes=_coerce_string_set(scopes, "scopes", "scope"),
            effects=_coerce_string_set(effects, "effects", "effect"),
            risk=_coerce(risk, Risk, "risk"),
            confirmation=_coerce(confirmation, Confirmation, "confirmation"),
            idempotency=_coerce(idempotency, Idempotency, "idempotency"),
            policies=tuple(policies),
        )

    def has_effect(self, effect: str) -> bool:
        """Whether this capability declares ``effect``."""
        return effect in self.effects

    def requires_scope(self, scope: str) -> bool:
        """Whether this capability declares ``scope`` as required.

        Reports a declaration. Deciding whether a caller holds it is the
        policy engine's job, not this type's (ADR 0008).
        """
        return scope in self.scopes

    def __str__(self) -> str:
        return str(self.id)
