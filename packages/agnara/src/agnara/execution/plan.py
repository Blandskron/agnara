"""Compiled, protocol-neutral execution metadata for one capability."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import field
from types import MappingProxyType
from typing import Any, get_type_hints

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.definition import CapabilityDefinition
from agnara.capability.metadata import Confirmation
from agnara.core.di import DIRegistry, compile_dag
from agnara.errors import DefinitionError
from agnara.execution.context import ExecutionContext
from agnara.execution.telemetry import TelemetryHook
from agnara.policy import ConfirmationVerifier, Policy
from agnara.policy.confirmation import ConfirmationPolicy

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
    hooks: tuple[TelemetryHook, ...] = ()
    policies: tuple[Policy, ...] = ()
    dependency_parameters: frozenset[str] = field(init=False)
    context_parameters: tuple[str, ...] = field(init=False)
    protected_parameters: frozenset[str] = field(init=False)

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

        direct_dependencies = frozenset(immutable_deps.get(self.definition.handler, ()))
        hints = get_type_hints(self.definition.handler)
        dependency_parameters = frozenset(
            name
            for name, annotation in hints.items()
            if name != "return" and annotation in direct_dependencies
        )
        context_parameters = tuple(
            name
            for name, annotation in hints.items()
            if name != "return" and annotation is ExecutionContext
        )
        object.__setattr__(self, "dependency_parameters", dependency_parameters)
        object.__setattr__(self, "context_parameters", context_parameters)
        object.__setattr__(
            self,
            "protected_parameters",
            dependency_parameters.union(context_parameters),
        )

    @classmethod
    def compile(
        cls,
        definition: CapabilityDefinition,
        registry: DIRegistry,
        hooks: Sequence[TelemetryHook] = (),
        confirmation_verifier: ConfirmationVerifier | None = None,
    ) -> ExecutionPlan:
        """Compile and validate the complete provider graph for ``definition``."""
        if not isinstance(definition, CapabilityDefinition):
            raise DefinitionError(
                f"definition must be a CapabilityDefinition, got {type(definition).__name__}"
            )
        if not isinstance(registry, DIRegistry):
            raise DefinitionError(f"registry must be a DIRegistry, got {type(registry).__name__}")
        policies = list(definition.policies)
        if definition.confirmation is Confirmation.POLICY and not policies:
            raise DefinitionError(
                f"capability {definition.id} declares policy confirmation "
                "but has no explicit policies"
            )
        if definition.confirmation is Confirmation.REQUIRED:
            if confirmation_verifier is None:
                raise DefinitionError(
                    f"capability {definition.id} requires a confirmation verifier"
                )
            policies.append(ConfirmationPolicy(definition.id, confirmation_verifier))
        return cls(
            definition=definition,
            target_deps=compile_dag(registry, [definition.handler]),
            hooks=tuple(hooks),
            policies=tuple(policies),
        )

    @property
    def dependencies(self) -> tuple[type, ...]:
        """Direct dependency types in handler-signature order."""
        return tuple(self.target_deps.get(self.definition.handler, ()))
