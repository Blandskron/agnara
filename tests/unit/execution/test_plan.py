from collections.abc import Callable
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import (
    DependencyCycleError,
    DependencyResolutionError,
    DIRegistry,
    provider,
)
from agnara.errors import DefinitionError
from agnara.execution import ExecutionPlan


class Database:
    pass


class Repository:
    pass


@provider()
def provide_database() -> Database:
    return Database()


@provider()
def provide_repository(database: Database) -> Repository:
    return Repository()


def define(handler: Callable[..., Any]) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=CapabilityId("payments", "refund"),
        handler=handler,
    )


def test_plan_compiles_direct_dependencies_in_signature_order() -> None:
    registry = DIRegistry()
    registry.bind(Database, provide_database)
    registry.bind(Repository, provide_repository)

    def refund(command: dict[str, object], repository: Repository, database: Database) -> None:
        pass

    capability = define(refund)
    plan = ExecutionPlan(capability, registry)

    assert plan.capability is capability
    assert plan.dependencies == (Repository, Database)


def test_plan_does_not_retain_mutable_registry_state() -> None:
    registry = DIRegistry()
    registry.bind(Database, provide_database)

    def refund(database: Database) -> None:
        pass

    plan = ExecutionPlan(define(refund), registry)

    registry.bind(Repository, provide_repository)

    assert plan.dependencies == (Database,)
    assert not hasattr(plan, "registry")


def test_plan_is_frozen_and_slotted() -> None:
    registry = DIRegistry()

    def refund(command: dict[str, object]) -> None:
        pass

    plan = ExecutionPlan(define(refund), registry)

    assert not hasattr(plan, "__dict__")
    with pytest.raises(FrozenInstanceError, match="cannot assign to field 'dependencies'"):
        plan.dependencies = ()


@pytest.mark.parametrize(
    ("capability", "registry", "message"),
    [
        (object(), DIRegistry(), "capability must be a CapabilityDefinition"),
        (define(lambda: None), object(), "registry must be a DIRegistry"),
    ],
)
def test_plan_rejects_invalid_constructor_inputs(
    capability: object, registry: object, message: str
) -> None:
    with pytest.raises(DefinitionError, match=message):
        ExecutionPlan(capability, registry)  # type: ignore


def test_plan_rejects_provider_cycle_during_compilation() -> None:
    class ServiceA:
        pass

    class ServiceB:
        pass

    @provider()
    def provide_a(service_b: ServiceB) -> ServiceA:
        return ServiceA()

    @provider()
    def provide_b(service_a: ServiceA) -> ServiceB:
        return ServiceB()

    registry = DIRegistry()
    registry.bind(ServiceA, provide_a)
    registry.bind(ServiceB, provide_b)

    def refund(service_a: ServiceA) -> None:
        pass

    with pytest.raises(DependencyCycleError, match="Dependency cycle detected"):
        ExecutionPlan(define(refund), registry)


def test_plan_rejects_unbound_provider_dependency_during_compilation() -> None:
    class Missing:
        pass

    @provider()
    def invalid_database(missing: Missing) -> Database:
        return Database()

    registry = DIRegistry()
    registry.bind(Database, invalid_database)

    def refund(database: Database) -> None:
        pass

    with pytest.raises(
        DependencyResolutionError,
        match="Providers can only depend on other registered providers",
    ):
        ExecutionPlan(define(refund), registry)
