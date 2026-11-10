"""Partial callable providers preserve execution kind, binding and ownership."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from functools import partial

import pytest

from agnara import Agnara, DefinitionError, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    Success,
    invoke_result,
)


class Seed:
    pass


class Resource:
    def __init__(self, owner, label: str, seed: Seed, suffix: str):
        self.owner = owner
        self.label = label
        self.seed = seed
        self.suffix = suffix
        self.closed = False


class Factory:
    def __init__(self):
        self.events: list[str] = []
        self.resources: list[Resource] = []

    def acquire(self, label: str, seed: Seed, suffix: str) -> Resource:
        self.events.append("open")
        resource = Resource(self, label, seed, suffix)
        self.resources.append(resource)
        return resource

    def close(self, resource: Resource) -> None:
        resource.closed = True
        self.events.append("close")


class SyncFactory(Factory):
    def __call__(self, label: str, seed: Seed, *, suffix: str) -> Resource:
        return self.acquire(label, seed, suffix)


class AsyncFactory(Factory):
    async def __call__(self, label: str, seed: Seed, *, suffix: str) -> Resource:
        await asyncio.sleep(0)
        return self.acquire(label, seed, suffix)


class GeneratorFactory(Factory):
    def __call__(self, label: str, seed: Seed, *, suffix: str) -> Iterator[Resource]:
        resource = self.acquire(label, seed, suffix)
        try:
            yield resource
        finally:
            self.close(resource)


class AsyncGeneratorFactory(Factory):
    async def __call__(self, label: str, seed: Seed, *, suffix: str) -> AsyncIterator[Resource]:
        resource = self.acquire(label, seed, suffix)
        try:
            yield resource
        finally:
            await asyncio.sleep(0)
            self.close(resource)


FACTORIES = (SyncFactory, AsyncFactory, GeneratorFactory, AsyncGeneratorFactory)


@pytest.mark.parametrize("factory_type", FACTORIES)
@pytest.mark.parametrize("scope", [Scope.INVOCATION, Scope.SINGLETON])
def test_partial_callable_values_binding_kind_and_lifecycle(factory_type, scope) -> None:
    async def run() -> None:
        before = asyncio.all_tasks()
        seed = Seed()
        factory = factory_type()
        wrapped = partial(partial(factory, "fixed"), seed=Seed(), suffix="untrusted default")
        definition = provider(scope=scope)(wrapped)
        assert definition.func is wrapped
        assert definition.provider_type is provider()(factory.__call__).provider_type
        assert definition.return_type is Resource
        registry = DIRegistry()

        @provider(scope=Scope.SINGLETON)
        def provide_seed() -> Seed:
            return seed

        @provider(scope=Scope.SINGLETON)
        def provide_suffix() -> str:
            return "injected"

        registry.bind(Seed, provide_seed)
        registry.bind(str, provide_suffix)
        registry.bind(Resource, definition)
        entered = asyncio.Event()
        app = Agnara("partial_objects")

        @app.capability(output=int, scopes={"read"})
        async def work(
            value: int, resource: Resource, alias: Resource, context: ExecutionContext
        ) -> int:
            assert isinstance(context, ExecutionContext)
            assert resource is alias and resource.owner is factory and not resource.closed
            assert (resource.label, resource.seed, resource.suffix) == ("fixed", seed, "injected")
            factory.events.append("handler")
            if value == 2:
                raise RuntimeError("private partial callable diagnostic")
            if value == 3:
                entered.set()
                await asyncio.Event().wait()
            return value

        plan = ExecutionPlan.compile(app.compile()["partial_objects.work"], registry)
        assert list(plan.input_schemas) == ["value"]
        assert plan.context_parameters == ("context",)
        assert factory.events == []
        container = DIContainer(registry)

        async def call(value, *, authorized=True):
            return await invoke_result(
                plan,
                ExecutionContext(
                    Invocation(plan.definition.id, {"value": value}, {}),
                    container,
                    principal=Principal("fixture", scopes={"read"} if authorized else set()),
                ),
            )

        generating = factory_type in (GeneratorFactory, AsyncGeneratorFactory)
        singleton = scope is Scope.SINGLETON
        try:
            async with asyncio.timeout(5):
                denied = await call(1, authorized=False)
                invalid = await call("bad")
                assert isinstance(denied, Failure) and denied.code is FailureCode.FORBIDDEN
                assert isinstance(invalid, Failure) and invalid.code is FailureCode.INVALID_INPUT
                assert factory.events == []
                assert await call(1) == Success(1)
                assert await call(2) == Failure(
                    FailureCode.INTERNAL_FAILURE, "capability invocation failed"
                )
                async with asyncio.TaskGroup() as owned:
                    task = owned.create_task(call(3))
                    await entered.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                assert task.cancelled()
                assert len(factory.resources) == (1 if singleton else 3)
                assert len({id(resource) for resource in factory.resources}) == len(
                    factory.resources
                )
                assert all(
                    resource.closed is (generating and not singleton)
                    for resource in factory.resources
                )
                trace = ["open", "handler"] + (["close"] if generating else [])
                assert factory.events == (
                    ["open", "handler", "handler", "handler"] if singleton else trace * 3
                )
        finally:
            await container.aclose()
        assert all(resource.closed is generating for resource in factory.resources)
        if singleton and generating:
            assert factory.events == ["open", "handler", "handler", "handler", "close"]
        assert asyncio.all_tasks() == before

    asyncio.run(run())


@pytest.mark.parametrize("violation", ["cycle", "scope"])
def test_partial_callable_real_dependency_graph_refusals(violation) -> None:
    factory = GeneratorFactory()
    registry = DIRegistry()

    @provider()
    def provide_seed(resource: Resource) -> Seed:
        return resource.seed

    @provider(scope=Scope.SINGLETON)
    def provide_suffix() -> str:
        return "injected"

    registry.bind(Seed, provide_seed)
    registry.bind(str, provide_suffix)
    registry.bind(
        Resource,
        provider(scope=Scope.SINGLETON if violation == "scope" else Scope.INVOCATION)(
            partial(factory, "fixed")
        ),
    )
    app = Agnara("graph_refusal")

    @app.capability(output=int)
    def read(resource: Resource) -> int:
        raise AssertionError("invalid graphs must fail before invocation")

    message = "Dependency cycle detected" if violation == "cycle" else "invocation-scoped"
    with pytest.raises(DefinitionError, match=message):
        ExecutionPlan.compile(app.compile()["graph_refusal.read"], registry)
    assert factory.events == []


def test_partial_class_constructor_keeps_its_synchronous_kind() -> None:
    class Constructor:
        def __new__(cls, label: str) -> Seed:
            assert label == "fixed"
            return Seed()

        async def __call__(self) -> Resource:
            raise AssertionError("class construction must not inspect the instance call kind")

    wrapped = partial(Constructor, "fixed")
    definition = provider()(wrapped)
    assert definition.func is wrapped
    assert definition.provider_type.value == "sync_function"
    assert definition.return_type is Seed
    assert isinstance(definition.func(), Seed)
