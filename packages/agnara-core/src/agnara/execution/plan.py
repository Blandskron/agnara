"""Compiled, protocol-neutral execution metadata for one capability."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.definition import CapabilityDefinition
from agnara.core.di import DIRegistry, compile_dag
from agnara.errors import DefinitionError

__all__ = ["ExecutionPlan"]


@frozen_slots_dataclass
class ExecutionPlan:
    """An immutable capability plan compiled before runtime invocation.

    ``target_deps`` preserves the mapping consumed by ``DIContainer`` while
    copying every dependency collection to a tuple and wrapping the mapping
    in a read-only proxy. The mutable DI registry is deliberately not retained.
    """

    definition: CapabilityDefinition
    target_deps: Mapping[Callable[..., Any], Sequence[type]]

    def __post_init__(self) -> None:
        if not isinstance(self.definition, CapabilityDefinition):
            raise DefinitionError(
                f"definition must be a CapabilityDefinition, got {type(self.definition).__name__}"
            )
        if not isinstance(self.target_deps, Mapping):
            raise DefinitionError(
                f"target_deps must be a mapping, got {type(self.target_deps).__name__}"
            )

        immutable_deps = {
            target: tuple(dependencies) for target, dependencies in self.target_deps.items()
        }
        object.__setattr__(self, "target_deps", MappingProxyType(immutable_deps))

    @classmethod
    def compile(cls, definition: CapabilityDefinition, registry: DIRegistry) -> ExecutionPlan:
        """Compile and validate the complete provider graph for ``definition``."""
        if not isinstance(definition, CapabilityDefinition):
            raise DefinitionError(
                f"definition must be a CapabilityDefinition, got {type(definition).__name__}"
            )
        if not isinstance(registry, DIRegistry):
            raise DefinitionError(f"registry must be a DIRegistry, got {type(registry).__name__}")
        return cls(
            definition=definition,
            target_deps=compile_dag(registry, [definition.handler]),
        )

    @property
    def dependencies(self) -> tuple[type, ...]:
        """Direct dependency types in handler-signature order."""
        return tuple(self.target_deps.get(self.definition.handler, ()))
