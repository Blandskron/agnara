"""Partial signatures preserve the wrapped callable's remaining contracts."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from functools import partial

import pytest

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.errors import DefinitionError
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    Success,
    invoke_result,
)
from agnara.introspection import describe_app


class Seed:
    def __init__(self):
        self.events: list[str] = []
        self.waiting = asyncio.Event()


class Resource:
    def __init__(self, label: str, seed: Seed):
        self.label = label
        self.seed = seed
        self.closed = False
        seed.events.append("resource.open")

    def close(self) -> None:
        self.closed = True
        self.seed.events.append("resource.close")


def sync_resource(label: str, seed: Seed) -> Resource:
    return Resource(label, seed)


async def async_resource(label: str, seed: Seed) -> Resource:
    await asyncio.sleep(0)
    return Resource(label, seed)


def generator_resource(label: str, seed: Seed) -> Iterator[Resource]:
    resource = Resource(label, seed)
    try:
        yield resource
    finally:
        resource.close()


async def async_generator_resource(label: str, seed: Seed) -> AsyncIterator[Resource]:
    resource = Resource(label, seed)
    try:
        yield resource
    finally:
        await asyncio.sleep(0)
        resource.close()


async def handle(fixed: str, value: int, resource: Resource, context: ExecutionContext) -> int:
    assert fixed == "handler" and resource.label == "resource"
    assert isinstance(context, ExecutionContext) and not resource.closed
    resource.seed.events.append("handler")
    if value == 2:
        raise RuntimeError("private partial handler diagnostic")
    if value == 3:
        resource.seed.waiting.set()
        await asyncio.Event().wait()
    return value


def dependencies(seed: Seed, factory) -> DIRegistry:
    registry = DIRegistry()

    @provider(scope=Scope.SINGLETON)
    def seed_provider() -> Iterator[Seed]:
        seed.events.append("seed.open")
        try:
            yield seed
        finally:
            seed.events.append("seed.close")

    @provider()
    def phantom_string() -> str:
        raise AssertionError("a positionally bound parameter must not become a dependency")

    registry.bind(Seed, seed_provider)
    registry.bind(str, phantom_string)
    registry.bind(Resource, provider()(factory))
    return registry


@pytest.mark.parametrize(
    "factory", [sync_resource, async_resource, generator_resource, async_generator_resource]
)
def test_partial_contracts_values_refusals_and_resource_lifecycle(factory) -> None:
    async def run() -> None:
        before = asyncio.all_tasks()
        seed = Seed()
        wrapped_provider = partial(factory, "resource")
        registry = dependencies(seed, wrapped_provider)
        wrapped_handler = partial(handle, "handler")
        app = Agnara("partials")
        app.capability(name="work", output=int, scopes={"read"})(wrapped_handler)
        plan = ExecutionPlan.compile(app.compile()["partials.work"], registry)
        assert plan.definition.handler is wrapped_handler
        registered = registry.get_provider(Resource)
        assert registered is not None and registered.func is wrapped_provider
        assert list(plan.input_schemas) == ["value"]
        assert plan.context_parameters == ("context",)
        assert plan.dependency_parameters == frozenset({"resource"})
        described = describe_app(app, [plan], dependencies=registry).capabilities[0]
        assert [item.name for item in described.inputs] == ["value"]
        assert [item.parameter for item in described.dependencies] == ["resource"]
        assert seed.events == []
        container = DIContainer(registry)

        async def call(payload, *, authorized=True):
            return await invoke_result(
                plan,
                ExecutionContext(
                    Invocation(plan.definition.id, payload, {}),
                    container,
                    principal=Principal("fixture", scopes={"read"} if authorized else set()),
                ),
            )

        generating = factory in (generator_resource, async_generator_resource)
        trace = ["resource.open", "handler"] + (["resource.close"] if generating else [])
        try:
            async with asyncio.timeout(5):
                denied = await call({"value": 1}, authorized=False)
                assert isinstance(denied, Failure) and denied.code is FailureCode.FORBIDDEN
                for payload in (
                    {"value": "bad"},
                    {"value": 1, "resource": "forged"},
                    {"value": 1, "context": "forged"},
                ):
                    refused = await call(payload)
                    assert (
                        isinstance(refused, Failure) and refused.code is FailureCode.INVALID_INPUT
                    )
                assert seed.events == []
                assert await call({"value": 1}) == Success(1)
                assert await call({"value": 2}) == Failure(
                    FailureCode.INTERNAL_FAILURE, "capability invocation failed"
                )
                async with asyncio.TaskGroup() as owned:
                    task = owned.create_task(call({"value": 3}))
                    await seed.waiting.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                assert task.cancelled()
                assert seed.events == ["seed.open", *trace * 3]
        finally:
            await container.aclose()
        assert seed.events == ["seed.open", *trace * 3, "seed.close"]
        assert asyncio.all_tasks() == before

    asyncio.run(run())


class BoundFactory:
    def create(self, label: str, seed: Seed) -> Iterator[Resource]:
        yield from generator_resource(label, seed)


class BoundHandler:
    def read(self, fixed: str, value: int, resource: Resource, context: ExecutionContext) -> int:
        assert fixed == "handler" and isinstance(context, ExecutionContext)
        assert resource.label == "resource" and not resource.closed
        resource.seed.events.append("handler")
        return value


def test_bound_methods_nested_partials_and_keyword_defaults_preserve_di() -> None:
    async def run() -> None:
        seed = Seed()
        foreign = Seed()
        wrapped_provider = partial(partial(BoundFactory().create, "resource"), seed=foreign)
        registry = dependencies(seed, wrapped_provider)
        untrusted_default = Resource("untrusted", foreign)
        foreign_events = tuple(foreign.events)
        wrapped_handler = partial(
            partial(BoundHandler().read, "handler"), value=5, resource=untrusted_default
        )
        app = Agnara("partial_defaults")
        app.capability(name="read", output=int)(wrapped_handler)
        plan = ExecutionPlan.compile(app.compile()["partial_defaults.read"], registry)
        assert plan.required_inputs == frozenset()
        assert list(plan.input_schemas) == ["value"]
        container = DIContainer(registry)
        try:
            async with asyncio.timeout(5):
                for payload, expected in (({}, 5), ({"value": 7}, 7)):
                    assert await invoke_result(
                        plan,
                        ExecutionContext(Invocation(plan.definition.id, payload, {}), container),
                    ) == Success(expected)
                # Explicit DI overrides both the handler and provider defaults.
                assert tuple(foreign.events) == foreign_events
        finally:
            await container.aclose()
        assert seed.events == [
            "seed.open",
            *["resource.open", "handler", "resource.close"] * 2,
            "seed.close",
        ]

    asyncio.run(run())


def missing(label: str, seed) -> Resource:
    raise AssertionError("startup validation must not construct providers")


def unresolved(label: str, seed: Seed) -> Resource:
    raise AssertionError("startup validation must not construct providers")


unresolved.__annotations__["seed"] = "NeverDefined"


def positional(label: str, seed: Seed, /) -> Resource:
    raise AssertionError("startup validation must not construct providers")


def variadic(label: str, *seed: Seed) -> Resource:
    raise AssertionError("startup validation must not construct providers")


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (missing, "requires a type annotation"),
        (unresolved, "cannot resolve the type annotations.*NameError"),
        (positional, "must be an explicit"),
        (variadic, "must be an explicit"),
    ],
)
def test_invalid_remaining_provider_contracts_still_fail_at_startup(factory, message) -> None:
    seed = Seed()
    registry = dependencies(seed, partial(factory, "resource"))
    app = Agnara("invalid_partial")
    app.capability(name="work", output=int)(partial(handle, "handler"))
    with pytest.raises(DefinitionError, match=message):
        ExecutionPlan.compile(app.compile()["invalid_partial.work"], registry)
    assert seed.events == []


def cyclic(label: str, resource: Resource) -> Resource:
    raise AssertionError("a dependency cycle must fail before provider effects")


@pytest.mark.parametrize(
    ("violation", "message"),
    [
        ("unbound", "requires unbound parameter"),
        ("captive", "A singleton may only depend on other singletons"),
        ("cycle", "Dependency cycle detected"),
    ],
)
def test_partial_providers_preserve_graph_and_scope_refusals(violation, message) -> None:
    seed = Seed()
    registry = DIRegistry()

    @provider()
    def seed_provider() -> Seed:
        seed.events.append("unexpected acquisition")
        return seed

    if violation != "unbound":
        registry.bind(Seed, seed_provider)
    registry.bind(
        Resource,
        provider(scope=Scope.SINGLETON if violation == "captive" else Scope.INVOCATION)(
            partial(cyclic if violation == "cycle" else generator_resource, "resource")
        ),
    )
    app = Agnara("invalid_graph")
    app.capability(name="work", output=int)(partial(handle, "handler"))
    with pytest.raises(DefinitionError, match=message):
        ExecutionPlan.compile(app.compile()["invalid_graph.work"], registry)
    assert seed.events == []
