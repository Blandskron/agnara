"""Collection and lookup of capability definitions.

The registry has two phases, and they are two types rather than one type
with a flag:

``CapabilityRegistry``
    The startup collection phase. Definitions are registered here while the
    application is being assembled. Registration is guarded by a lock.

``FrozenCapabilityRegistry``
    The result of :meth:`CapabilityRegistry.freeze`. A read-only mapping
    with no mutable state, safe to share across threads without locking.

Two types rather than a ``frozen`` flag because ``register`` simply does not
exist on the frozen form, so misuse fails at type-check time instead of at
runtime, and "no mutable state" is a stronger claim than "a flag nobody has
flipped". ADR 0005 places the freeze at the end of startup compilation, and
PRINCIPLES.md P6 requires the frozen form to be safe under free-threaded
CPython.

Iteration order is registration order, in both phases. Determinism is part
of the contract: generated manifests, OpenAPI documents and MCP tool lists
are all derived from this order, and they should not reshuffle between runs.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Iterator, Mapping
from types import MappingProxyType

from agnara.capability.definition import CapabilityDefinition
from agnara.capability.identity import CapabilityId
from agnara.errors import (
    DefinitionError,
    DuplicateCapabilityError,
    RegistryFrozenError,
    UnknownCapabilityError,
)

__all__ = [
    "CapabilityRegistry",
    "FrozenCapabilityRegistry",
]

#: Anything that can name a capability in a lookup.
CapabilityKey = CapabilityId | str


def _as_id(key: CapabilityKey) -> CapabilityId:
    """Normalize a lookup key, accepting the dotted string form.

    ``docs/API_DESIGN.md`` section 17 shows ``app.capabilities["users.get"]``,
    so strings are part of the intended surface, not a convenience bolted on.
    """
    if isinstance(key, CapabilityId):
        return key
    return CapabilityId.parse(key)


def _missing(key: CapabilityKey) -> UnknownCapabilityError:
    return UnknownCapabilityError(f"no capability registered as {str(key)!r}")


class FrozenCapabilityRegistry(Mapping[CapabilityId, CapabilityDefinition]):
    """An immutable view of registered capabilities.

    Holds no mutable state, so concurrent readers need no synchronization.
    The definitions it contains are themselves frozen.
    """

    __slots__ = ("_definitions",)

    def __init__(self, definitions: Mapping[CapabilityId, CapabilityDefinition]) -> None:
        # Copy, then wrap. The copy detaches this view from whatever the
        # caller keeps mutating; the proxy stops anyone reaching through
        # `_definitions` to change it.
        self._definitions: Mapping[CapabilityId, CapabilityDefinition] = MappingProxyType(
            dict(definitions)
        )

    def __getitem__(self, key: CapabilityKey) -> CapabilityDefinition:
        try:
            return self._definitions[_as_id(key)]
        except KeyError:
            raise _missing(key) from None

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, CapabilityId | str):
            return False
        try:
            return _as_id(key) in self._definitions
        except DefinitionError:
            # An unparseable string simply is not a registered id.
            return False

    def __iter__(self) -> Iterator[CapabilityId]:
        return iter(self._definitions)

    def __len__(self) -> int:
        return len(self._definitions)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({len(self)} capabilities)"

    @property
    def namespaces(self) -> frozenset[str]:
        """Every namespace that owns at least one registered capability."""
        return frozenset(capability_id.namespace for capability_id in self._definitions)

    def in_namespace(self, namespace: str) -> tuple[CapabilityDefinition, ...]:
        """Registered capabilities owned by ``namespace``, in registration order."""
        return tuple(
            definition
            for capability_id, definition in self._definitions.items()
            if capability_id.namespace == namespace
        )

    def with_effect(self, effect: str) -> tuple[CapabilityDefinition, ...]:
        """Registered capabilities declaring ``effect``, in registration order.

        Useful for asking a project "what here writes to the database?" or
        "what is destructive?". It reports declarations, and a declaration
        is not an authorization decision (ADR 0008).
        """
        return tuple(
            definition for definition in self._definitions.values() if definition.has_effect(effect)
        )


class CapabilityRegistry:
    """Collects capability definitions during startup.

    Not safe to expose after compilation; call :meth:`freeze` and share the
    result instead.
    """

    __slots__ = ("_definitions", "_frozen", "_lock")

    def __init__(self, definitions: Iterable[CapabilityDefinition] = ()) -> None:
        self._definitions: dict[CapabilityId, CapabilityDefinition] = {}
        # Guards `_definitions` and `_frozen` together. Registration happens
        # during startup, which is usually single-threaded, but "usually" is
        # not a guarantee under free-threaded CPython (PRINCIPLES.md P6).
        self._lock = threading.Lock()
        self._frozen = False
        for definition in definitions:
            self.register(definition)

    @property
    def is_frozen(self) -> bool:
        """Whether :meth:`freeze` has been called."""
        return self._frozen

    def register(self, definition: CapabilityDefinition) -> CapabilityDefinition:
        """Register ``definition``, returning it so decorators can chain.

        Raises `DuplicateCapabilityError` if the id is already taken, and
        `RegistryFrozenError` if compilation has already frozen the registry.
        """
        if not isinstance(definition, CapabilityDefinition):
            raise TypeError(
                f"can only register a CapabilityDefinition, got {type(definition).__name__}"
            )
        with self._lock:
            if self._frozen:
                raise RegistryFrozenError(
                    f"cannot register {definition.id} after the registry was frozen; "
                    "registration belongs to startup compilation (ADR 0005)"
                )
            existing = self._definitions.get(definition.id)
            if existing is not None:
                raise DuplicateCapabilityError(
                    f"capability {definition.id} is already registered; "
                    "ids must be unique because policies, audit records and "
                    "agent manifests reference them"
                )
            self._definitions[definition.id] = definition
        return definition

    def freeze(self) -> FrozenCapabilityRegistry:
        """Close registration and return the immutable view.

        Idempotent: calling it again returns an equivalent view rather than
        failing, so a composition root does not have to track whether some
        other component already froze the registry.
        """
        with self._lock:
            self._frozen = True
            return FrozenCapabilityRegistry(self._definitions)

    def __getitem__(self, key: CapabilityKey) -> CapabilityDefinition:
        try:
            return self._definitions[_as_id(key)]
        except KeyError:
            raise _missing(key) from None

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, CapabilityId | str):
            return False
        try:
            return _as_id(key) in self._definitions
        except DefinitionError:
            return False

    def __iter__(self) -> Iterator[CapabilityId]:
        return iter(tuple(self._definitions))

    def __len__(self) -> int:
        return len(self._definitions)

    def __repr__(self) -> str:
        state = "frozen" if self._frozen else "open"
        return f"{type(self).__name__}({len(self)} capabilities, {state})"
