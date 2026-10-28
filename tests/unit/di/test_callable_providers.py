"""Callable provider instances retain their kind and resource ownership."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from functools import partial

import pytest

from agnara import Agnara, Principal
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
    def __init__(self, seed: Seed):
        self.seed = seed
        self.closed = False


class SeedFactory:
    def __init__(self, events: list[str]):
        self.events = events

    def __call__(self) -> Iterator[Seed]:
        self.events.append("seed.open")
        try:
            yield Seed()
        finally:
            self.events.append("seed.close")


class FactoryState:
    def __init__(self, events: list[str]):
        self.events = events
        self.resources: list[Resource] = []

    def acquire(self, seed: Seed) -> Resource:
        self.events.append("resource.open")
        result = Resource(seed)
        self.resources.append(result)
        return result

    def close(self, resource: Resource) -> None:
        resource.closed = True
        self.events.append("resource.close")


class SyncFactory(FactoryState):
    def __call__(self, seed: Seed) -> Resource:
        return self.acquire(seed)


class AsyncFactory(FactoryState):
    async def __call__(self, seed: Seed) -> Resource:
        await asyncio.sleep(0)
        return self.acquire(seed)


class GeneratorFactory(FactoryState):
    def __call__(self, seed: Seed) -> Iterator[Resource]:
        resource = self.acquire(seed)
        try:
            yield resource
        finally:
            self.close(resource)


class AsyncGeneratorFactory(FactoryState):
    async def __call__(self, seed: Seed) -> AsyncIterator[Resource]:
        resource = self.acquire(seed)
        try:
            yield resource
        finally:
            await asyncio.sleep(0)
            self.close(resource)


FACTORIES = (SyncFactory, AsyncFactory, GeneratorFactory, AsyncGeneratorFactory)


@pytest.mark.parametrize(
    ("factory_type", "kind"),
    tuple(
        zip(
            FACTORIES,
            ("sync_function", "async_function", "sync_generator", "async_generator"),
            strict=True,
        )
    ),
)
def test_callable_kind_and_original_identity(factory_type, kind) -> None:
    factory = factory_type([])
    definition = provider()(factory)
    reference = provider()(factory.__call__)
    assert definition.func is factory
    assert definition.provider_type is reference.provider_type
    assert definition.provider_type.value == kind
    assert definition.return_type is Resource
    assert factory.events == factory.resources == []


@pytest.mark.parametrize("factory_type", FACTORIES)
def test_bound_methods_and_partial_kinds_remain_compatible(factory_type) -> None:
    factory = factory_type([])
    method = provider()(factory.__call__)
    wrapped = provider()(partial(factory.__call__, seed=Seed()))
    assert wrapped.provider_type is method.provider_type
    assert wrapped.return_type is method.return_type is Resource
    assert factory.events == []


def test_class_constructor_remains_synchronous() -> None:
    class Constructor:
        def __new__(cls) -> Seed:
            return Seed()

        async def __call__(self) -> Resource:
            raise AssertionError("constructing a provider class must not invoke its instances")

    definition = provider()(Constructor)
    assert definition.func is Constructor
    assert definition.provider_type.value == "sync_function"
    assert definition.return_type is Seed


@pytest.mark.parametrize("factory_type", FACTORIES)
def test_invocation_values_refusals_failure_cancellation_and_cleanup(factory_type) -> None:
    async def run() -> None:
        before = asyncio.all_tasks()
        events: list[str] = []
        factory = factory_type(events)
        registry = DIRegistry()
        registry.bind(Seed, provider(scope=Scope.SINGLETON)(SeedFactory(events)))
        registry.bind(Resource, provider()(factory))
        app = Agnara("callable_providers")
        entered = asyncio.Event()

        @app.capability(output=int, scopes={"read"})
        async def work(value: int, resource: Resource, alias: Resource) -> int:
            assert isinstance(resource, Resource) and resource is alias
            assert not resource.closed
            events.append("handler")
            if value == 2:
                raise RuntimeError("private callable-provider diagnostic")
            if value == 3:
                entered.set()
                await asyncio.Event().wait()
            return value

        plan = ExecutionPlan.compile(app.compile()["callable_providers.work"], registry)
        assert events == []
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
        trace = ["resource.open", "handler"] + (["resource.close"] if generating else [])
        try:
            async with asyncio.timeout(5):
                denied = await call(1, authorized=False)
                invalid = await call("bad")
                assert isinstance(denied, Failure) and denied.code is FailureCode.FORBIDDEN
                assert isinstance(invalid, Failure) and invalid.code is FailureCode.INVALID_INPUT
                assert events == []
                assert await call(1) == Success(1)
                failed = await call(2)
                assert failed == Failure(
                    FailureCode.INTERNAL_FAILURE, "capability invocation failed"
                )
                async with asyncio.TaskGroup() as owned:
                    task = owned.create_task(call(3))
                    await entered.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                assert task.cancelled()
                assert events == ["seed.open", *trace * 3]
                assert len(factory.resources) == 3
                assert len({id(resource) for resource in factory.resources}) == 3
                assert all(
                    resource.seed is factory.resources[0].seed for resource in factory.resources
                )
                assert all(resource.closed is generating for resource in factory.resources)
        finally:
            await container.aclose()
        assert events == ["seed.open", *trace * 3, "seed.close"]
        assert asyncio.all_tasks() == before

    asyncio.run(run())


@pytest.mark.parametrize("factory_type", [GeneratorFactory, AsyncGeneratorFactory])
def test_singleton_callable_generator_reuses_until_container_close(factory_type) -> None:
    async def run() -> None:
        events: list[str] = []
        registry = DIRegistry()
        registry.bind(Seed, provider(scope=Scope.SINGLETON)(SeedFactory(events)))
        factory = factory_type(events)
        registry.bind(Resource, provider(scope=Scope.SINGLETON)(factory))
        app = Agnara("singleton_factory")

        @app.capability(output=bool)
        def read(resource: Resource) -> bool:
            return isinstance(resource, Resource) and not resource.closed

        plan = ExecutionPlan.compile(app.compile()["singleton_factory.read"], registry)
        container = DIContainer(registry)
        try:
            async with asyncio.timeout(5):
                for _ in range(2):
                    result = await invoke_result(
                        plan, ExecutionContext(Invocation(plan.definition.id, {}, {}), container)
                    )
                    assert result == Success(True)
                assert len(factory.resources) == 1 and not factory.resources[0].closed
                assert events == ["seed.open", "resource.open"]
        finally:
            await container.aclose()
        assert factory.resources[0].closed
        assert events == ["seed.open", "resource.open", "resource.close", "seed.close"]

    asyncio.run(run())
