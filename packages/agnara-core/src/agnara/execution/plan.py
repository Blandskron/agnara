"""Compiled, protocol-neutral execution metadata for one capability."""

from __future__ import annotations

from dataclasses import InitVar, field

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.definition import CapabilityDefinition
from agnara.core.di import DIRegistry, compile_dag
from agnara.errors import DefinitionError

__all__ = ["ExecutionPlan"]


@frozen_slots_dataclass
class ExecutionPlan:
    """Immutable startup-compiled metadata for one capability.

    The plan snapshots the capability's direct dependency types in handler
    signature order. ``compile_dag`` also traverses provider dependencies, so
    invalid provider graphs fail while the plan is constructed rather than on
    first invocation. The mutable registry is deliberately not retained.
    """

    capability: CapabilityDefinition
    registry: InitVar[DIRegistry]
    dependencies: tuple[type, ...] = field(init=False)

    def __post_init__(self, registry: DIRegistry) -> None:
        if not isinstance(self.capability, CapabilityDefinition):
            raise DefinitionError(
                f"capability must be a CapabilityDefinition, got {type(self.capability).__name__}"
            )
        if not isinstance(registry, DIRegistry):
            raise DefinitionError(f"registry must be a DIRegistry, got {type(registry).__name__}")

        compiled = compile_dag(registry, [self.capability.handler])
        object.__setattr__(
            self,
            "dependencies",
            tuple(compiled[self.capability.handler]),
        )
