from collections.abc import Callable
from typing import Any

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.definition import CapabilityDefinition
from agnara.core.di.compiler import compile_dag
from agnara.core.di.registry import DIRegistry

__all__ = ["ExecutionPlan"]


@frozen_slots_dataclass
class ExecutionPlan:
    """A compiled capability ready for invocation.

    Holds the original capability definition and the pre-computed dependency
    DAG so that the `DIContainer` can resolve dependencies quickly during
    execution without needing to re-compile them on the hot path.
    """

    definition: CapabilityDefinition
    target_deps: dict[Callable[..., Any], list[type]]

    @classmethod
    def compile(cls, definition: CapabilityDefinition, registry: DIRegistry) -> ExecutionPlan:
        """Compile a capability definition into an execution plan."""
        # Compile the dependency DAG for the capability's handler
        dag = compile_dag(registry, [definition.handler])
        return cls(definition=definition, target_deps=dag)
