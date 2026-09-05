"""Build an introspection snapshot from a compiled application.

The snapshot describes what was compiled, not what was declared: plans are
required, so a capability whose plan is missing is an error rather than a
capability silently published without its inputs, dependencies or policies.

Reflection happens here, once, at inspection time. This is a startup and
tooling path, never an invocation path (PRINCIPLES.md P5).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import get_type_hints

from agnara.application import Agnara
from agnara.capability.identity import CapabilityId
from agnara.core.di.compiler import _get_dependencies
from agnara.core.di.registry import DIRegistry
from agnara.execution.plan import ExecutionPlan
from agnara.introspection.descriptors import (
    AppDescriptor,
    CapabilityDescriptor,
    DependencyDescriptor,
    ExposureDescriptor,
    InputDescriptor,
    IntrospectionError,
    IntrospectionSnapshot,
    PolicyDescriptor,
    ProviderDescriptor,
    TypeReference,
)

__all__ = ["describe_app", "snapshot"]


def _plans_by_id(plans: Iterable[ExecutionPlan]) -> dict[CapabilityId, ExecutionPlan]:
    indexed: dict[CapabilityId, ExecutionPlan] = {}
    for plan in plans:
        if not isinstance(plan, ExecutionPlan):
            raise IntrospectionError(
                f"introspection plans must contain ExecutionPlan values, got {type(plan).__name__}"
            )
        capability_id = plan.definition.id
        if capability_id in indexed:
            raise IntrospectionError(f"duplicate execution plan for {capability_id}")
        indexed[capability_id] = plan
    return indexed


def _inputs(plan: ExecutionPlan) -> tuple[InputDescriptor, ...]:
    """Describe compiled inputs in handler-signature order."""
    return tuple(
        InputDescriptor.of(
            name,
            required=name in plan.required_inputs,
            schema=schema.json_schema(),
        )
        for name, schema in plan.input_schemas.items()
    )


def _dependencies(plan: ExecutionPlan) -> tuple[DependencyDescriptor, ...]:
    """Pair each dependency parameter with the type the plan bound to it.

    The plan keeps names and types separately, so the pairing is recovered
    from the same annotations the plan compiled from. Filtering by the plan's
    own ``dependency_parameters`` keeps a payload parameter out even when it
    happens to be annotated with a bound type.
    """
    hints = get_type_hints(plan.definition.handler)
    return tuple(
        DependencyDescriptor(name, TypeReference.of(annotation))
        for name, annotation in hints.items()
        if name in plan.dependency_parameters
    )


def _policies(plan: ExecutionPlan) -> tuple[PolicyDescriptor, ...]:
    return tuple(PolicyDescriptor(type(policy).__name__) for policy in plan.policies)


def _providers(registry: DIRegistry) -> tuple[ProviderDescriptor, ...]:
    """Describe every bound provider as a graph node, in binding order."""
    bindings = registry.all_bindings()
    return tuple(
        ProviderDescriptor(
            TypeReference.of(provides),
            provider.scope.value,
            provider.provider_type.value,
            tuple(
                TypeReference.of(required)
                for required in _get_dependencies(provider.func).values()
                if registry.is_bound(required)
            ),
        )
        for provides, provider in bindings.items()
    )


def _exposures(
    exposures: Mapping[str, Iterable[ExposureDescriptor]] | None,
    known: frozenset[str],
) -> dict[str, tuple[ExposureDescriptor, ...]]:
    """Attach adapter-contributed exposures, refusing one that names nothing.

    An unknown capability id is an error rather than a dropped entry: silently
    losing an exposure would understate what a capability is reachable through,
    which is exactly the fact a viewer is consulting the snapshot to learn.
    """
    if exposures is None:
        return {}
    if not isinstance(exposures, Mapping):
        raise IntrospectionError(
            f"introspection exposures must be a mapping, got {type(exposures).__name__}"
        )
    attached: dict[str, tuple[ExposureDescriptor, ...]] = {}
    for capability_id, described in exposures.items():
        if capability_id not in known:
            raise IntrospectionError(
                f"introspection exposures name unknown capability {capability_id!r}"
            )
        collected = tuple(described)
        for exposure in collected:
            if not isinstance(exposure, ExposureDescriptor):
                raise IntrospectionError(
                    "introspection exposures must contain ExposureDescriptor values, got "
                    f"{type(exposure).__name__}"
                )
        attached[capability_id] = collected
    return attached


def describe_app(
    app: Agnara,
    plans: Iterable[ExecutionPlan],
    *,
    exposures: Mapping[str, Iterable[ExposureDescriptor]] | None = None,
    dependencies: DIRegistry | None = None,
) -> AppDescriptor:
    """Describe one compiled application as immutable descriptors.

    Every declared capability must have a compiled plan. Extra plans are
    permitted, so a caller may pass a project-wide plan set while describing
    one application. ``exposures`` is keyed by capability id and supplied by
    whoever owns the adapters, because core imports none of them.
    ``dependencies`` adds the provider graph; without it a capability's
    dependencies are still named, but their scopes and relationships are not.
    """
    if not isinstance(app, Agnara):
        raise IntrospectionError(f"app must be an Agnara application, got {type(app).__name__}")
    if dependencies is not None and not isinstance(dependencies, DIRegistry):
        raise IntrospectionError(
            f"dependencies must be a DIRegistry or None, got {type(dependencies).__name__}"
        )
    indexed = _plans_by_id(plans)
    registry = app.capabilities
    known = frozenset(str(capability_id) for capability_id in registry)
    attached = _exposures(exposures, known)

    described: list[CapabilityDescriptor] = []
    for capability_id in registry:
        definition = registry[capability_id]
        plan = indexed.get(capability_id)
        if plan is None:
            raise IntrospectionError(
                f"capability {capability_id} has no execution plan; introspection describes a "
                "compiled application"
            )
        if plan.definition is not definition:
            raise IntrospectionError(
                f"the execution plan for {capability_id} does not retain its declared capability"
            )
        described.append(
            CapabilityDescriptor(
                id=str(capability_id),
                description=definition.description,
                effects=tuple(sorted(definition.effects)),
                scopes=tuple(sorted(definition.scopes)),
                risk=definition.risk.value,
                confirmation=definition.confirmation.value,
                idempotency=definition.idempotency.value,
                inputs=_inputs(plan),
                dependencies=_dependencies(plan),
                policies=_policies(plan),
                exposures=attached.get(str(capability_id), ()),
            )
        )
    return AppDescriptor(
        name=app.name,
        capabilities=tuple(described),
        providers=() if dependencies is None else _providers(dependencies),
    )


def snapshot(
    apps: Iterable[AppDescriptor],
    *,
    project: str | None = None,
) -> IntrospectionSnapshot:
    """Assemble one versioned snapshot from already-described applications.

    Application order is the caller's, because it is the only order that
    carries meaning until a project descriptor exists to define one.
    """
    described = tuple(apps)
    for app in described:
        if not isinstance(app, AppDescriptor):
            raise IntrospectionError(
                f"introspection apps must contain AppDescriptor values, got {type(app).__name__}"
            )
    return IntrospectionSnapshot(apps=described, project=project)
