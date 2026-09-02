import asyncio
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.capability.metadata import Confirmation
from agnara.core.di import (
    DependencyCycleError,
    DependencyResolutionError,
    DIContainer,
    DIRegistry,
    provider,
)
from agnara.errors import DefinitionError
from agnara.execution import ExecutionPlan
from agnara.policy import (
    ConfirmationEvidence,
    ConfirmationVerdict,
    PolicyFailure,
    PolicyResult,
)
from agnara.policy.confirmation import ConfirmationPolicy


class DenyPolicy:
    async def evaluate(self, context) -> PolicyResult:
        return PolicyFailure("denied")


class ValidVerifier:
    async def verify(
        self,
        evidence: ConfirmationEvidence,
        *,
        capability_id,
        invocation,
        principal,
    ) -> ConfirmationVerdict:
        return ConfirmationVerdict.VALID


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
    plan = ExecutionPlan.compile(capability, registry)

    assert plan.definition is capability
    assert plan.target_deps[refund] == (Repository, Database)
    assert plan.dependencies == (Repository, Database)


def test_plan_copies_mutable_compiler_output() -> None:
    def refund(database: Database) -> None:
        pass

    dependencies = [Database]
    source = {refund: dependencies}
    plan = ExecutionPlan(definition=define(refund), target_deps=source)

    dependencies.append(Repository)
    source.clear()

    assert plan.target_deps[refund] == (Database,)


def test_plan_dependency_mapping_is_read_only() -> None:
    def refund(database: Database) -> None:
        pass

    plan = ExecutionPlan(definition=define(refund), target_deps={refund: [Database]})

    with pytest.raises(TypeError, match="does not support item assignment"):
        plan.target_deps[refund] = ()  # type: ignore


def test_compiled_plan_is_consumed_directly_by_di_container() -> None:
    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Database, provide_database)

        def refund(database: Database) -> None:
            pass

        plan = ExecutionPlan.compile(define(refund), registry)
        container = DIContainer(registry)

        async with container.resolve_dependencies(refund, plan.target_deps) as resolved:
            assert isinstance(resolved["database"], Database)

        await container.aclose()

    asyncio.run(run_test())


def test_plan_is_frozen_and_slotted() -> None:
    def refund(command: dict[str, object]) -> None:
        pass

    plan = ExecutionPlan.compile(define(refund), DIRegistry())

    assert not hasattr(plan, "__dict__")
    with pytest.raises(FrozenInstanceError, match="cannot assign to field 'target_deps'"):
        plan.target_deps = {}  # type: ignore[misc]


@pytest.mark.parametrize(
    ("definition", "registry", "message"),
    [
        (object(), DIRegistry(), "definition must be a CapabilityDefinition"),
        (define(lambda: None), object(), "registry must be a DIRegistry"),
    ],
)
def test_compile_rejects_invalid_inputs(definition: object, registry: object, message: str) -> None:
    with pytest.raises(DefinitionError, match=message):
        ExecutionPlan.compile(definition, registry)  # type: ignore


def test_constructor_rejects_non_mapping_dependencies() -> None:
    with pytest.raises(DefinitionError, match="target_deps must be a mapping"):
        ExecutionPlan(definition=define(lambda: None), target_deps=object())  # type: ignore


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
        ExecutionPlan.compile(define(refund), registry)


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
        ExecutionPlan.compile(define(refund), registry)


def test_plan_compiles_explicit_policies_in_declaration_order() -> None:
    first = DenyPolicy()
    second = DenyPolicy()
    capability = CapabilityDefinition(
        id=CapabilityId("payments", "refund"),
        handler=lambda: None,
        policies=(first, second),
    )

    assert ExecutionPlan.compile(capability, DIRegistry()).policies == (first, second)


def test_required_confirmation_appends_gate_after_explicit_policies() -> None:
    explicit = DenyPolicy()
    capability = CapabilityDefinition(
        id=CapabilityId("payments", "refund"),
        handler=lambda: None,
        confirmation=Confirmation.REQUIRED,
        policies=(explicit,),
    )

    plan = ExecutionPlan.compile(
        capability,
        DIRegistry(),
        confirmation_verifier=ValidVerifier(),
    )

    assert plan.policies[0] is explicit
    assert isinstance(plan.policies[1], ConfirmationPolicy)


def test_required_confirmation_without_verifier_fails_at_compilation() -> None:
    capability = CapabilityDefinition(
        id=CapabilityId("payments", "refund"),
        handler=lambda: None,
        confirmation=Confirmation.REQUIRED,
    )

    with pytest.raises(DefinitionError, match="requires a confirmation verifier"):
        ExecutionPlan.compile(capability, DIRegistry())


def test_policy_confirmation_uses_only_explicit_application_policies() -> None:
    explicit = DenyPolicy()
    capability = CapabilityDefinition(
        id=CapabilityId("payments", "refund"),
        handler=lambda: None,
        confirmation=Confirmation.POLICY,
        policies=(explicit,),
    )

    assert ExecutionPlan.compile(capability, DIRegistry()).policies == (explicit,)


def test_policy_confirmation_without_explicit_policy_fails_at_compilation() -> None:
    capability = CapabilityDefinition(
        id=CapabilityId("payments", "refund"),
        handler=lambda: None,
        confirmation=Confirmation.POLICY,
    )

    with pytest.raises(DefinitionError, match="has no explicit policies"):
        ExecutionPlan.compile(capability, DIRegistry())
