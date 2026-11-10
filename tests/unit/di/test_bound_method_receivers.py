"""Bound receiver annotations never introduce a second dependency receiver."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

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
from agnara.introspection import describe_app


class Seed:
    def __init__(self):
        self.events: list[str] = []
        self.resources: list[Resource] = []
        self.waiting = asyncio.Event()


class Resource:
    def __init__(self, owner: object, seed: Seed):
        self.owner = owner
        self.seed = seed
        self.closed = False
        seed.resources.append(self)
        seed.events.append("resource.open")

    def close(self) -> None:
        self.closed = True
        self.seed.events.append("resource.close")


class MethodFactory:
    def sync(self: MethodFactory, seed: Seed) -> Resource:
        return Resource(self, seed)

    async def async_create(self: MethodFactory, seed: Seed) -> Resource:
        await asyncio.sleep(0)
        return Resource(self, seed)

    def generate(self: MethodFactory, seed: Seed) -> Iterator[Resource]:
        resource = Resource(self, seed)
        try:
            yield resource
        finally:
            resource.close()

    async def async_generate(self: MethodFactory, seed: Seed) -> AsyncIterator[Resource]:
        resource = Resource(self, seed)
        try:
            yield resource
        finally:
            await asyncio.sleep(0)
            resource.close()

    @classmethod
    def class_sync(cls: type[MethodFactory], seed: Seed) -> Resource:
        return Resource(cls, seed)

    @classmethod
    async def class_async_create(cls: type[MethodFactory], seed: Seed) -> Resource:
        await asyncio.sleep(0)
        return Resource(cls, seed)

    @classmethod
    def class_generate(cls: type[MethodFactory], seed: Seed) -> Iterator[Resource]:
        resource = Resource(cls, seed)
        try:
            yield resource
        finally:
            resource.close()

    @classmethod
    async def class_async_generate(cls: type[MethodFactory], seed: Seed) -> AsyncIterator[Resource]:
        resource = Resource(cls, seed)
        try:
            yield resource
        finally:
            await asyncio.sleep(0)
            resource.close()


def registry_for(seed: Seed, *, seed_scope=Scope.SINGLETON) -> DIRegistry:
    registry = DIRegistry()

    @provider(scope=seed_scope)
    def seed_provider() -> Iterator[Seed]:
        seed.events.append("seed.open")
        try:
            yield seed
        finally:
            seed.events.append("seed.close")

    @provider()
    def unwanted_receiver() -> MethodFactory:
        raise AssertionError("the already bound receiver must never be acquired")

    registry.bind(Seed, seed_provider)
    registry.bind(MethodFactory, unwanted_receiver)
    return registry


@pytest.mark.parametrize(
    "method_name",
    [
        "sync",
        "async_create",
        "generate",
        "async_generate",
        "class_sync",
        "class_async_create",
        "class_generate",
        "class_async_generate",
    ],
)
def test_bound_provider_kinds_preserve_owner_values_and_lifecycle(method_name) -> None:
    async def run() -> None:
        before = asyncio.all_tasks()
        seed = Seed()
        factory = MethodFactory()
        method = getattr(factory, method_name)
        registry = registry_for(seed)
        definition = provider()(method)
        assert definition.func is method
        registry.bind(Resource, definition)
        app = Agnara("method_providers")

        @app.capability(output=int, scopes={"read"})
        async def work(value: int, resource: Resource, alias: Resource) -> int:
            assert resource is alias and not resource.closed
            assert resource.owner is (
                MethodFactory if method_name.startswith("class_") else factory
            )
            seed.events.append("handler")
            if value == 2:
                raise RuntimeError("private method-provider diagnostic")
            if value == 3:
                seed.waiting.set()
                await asyncio.Event().wait()
            return value

        plan = ExecutionPlan.compile(app.compile()["method_providers.work"], registry)
        assert seed.events == []
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

        generating = "generate" in method_name
        trace = ["resource.open", "handler"] + (["resource.close"] if generating else [])
        try:
            async with asyncio.timeout(5):
                denied = await call(1, authorized=False)
                invalid = await call("bad")
                assert isinstance(denied, Failure) and denied.code is FailureCode.FORBIDDEN
                assert isinstance(invalid, Failure) and invalid.code is FailureCode.INVALID_INPUT
                assert seed.events == []
                assert await call(1) == Success(1)
                assert await call(2) == Failure(
                    FailureCode.INTERNAL_FAILURE, "capability invocation failed"
                )
                async with asyncio.TaskGroup() as owned:
                    task = owned.create_task(call(3))
                    await seed.waiting.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                assert task.cancelled()
                assert len(seed.resources) == len({id(item) for item in seed.resources}) == 3
                assert all(item.closed is generating for item in seed.resources)
                assert seed.events == ["seed.open", *trace * 3]
        finally:
            await container.aclose()
        assert seed.events == ["seed.open", *trace * 3, "seed.close"]
        assert asyncio.all_tasks() == before

    asyncio.run(run())


class BoundHandler:
    def read(
        receiver: BoundHandler, value: int, resource: Resource, context: ExecutionContext
    ) -> int:
        assert resource.owner is receiver and isinstance(context, ExecutionContext)
        resource.seed.events.append("handler")
        return value

    async def async_read(
        receiver: BoundHandler, value: int, resource: Resource, context: ExecutionContext
    ) -> int:
        await asyncio.sleep(0)
        return receiver.read(value, resource, context)


@pytest.mark.parametrize("method_name", ["read", "async_read"])
def test_bound_handler_contract_excludes_an_annotated_custom_receiver_name(method_name) -> None:
    async def run() -> None:
        seed = Seed()
        owner = BoundHandler()
        registry = registry_for(seed)

        @provider()
        def resource(seed: Seed) -> Iterator[Resource]:
            item = Resource(owner, seed)
            try:
                yield item
            finally:
                item.close()

        @provider()
        def phantom_handler() -> BoundHandler:
            raise AssertionError("the bound handler is not an invocation dependency")

        registry.bind(Resource, resource)
        registry.bind(BoundHandler, phantom_handler)
        handler = getattr(owner, method_name)
        app = Agnara("method_handlers")
        app.capability(name="read", output=int, scopes={"read"})(handler)
        plan = ExecutionPlan.compile(app.compile()["method_handlers.read"], registry)
        assert plan.definition.handler is handler
        assert plan.dependency_parameters == frozenset({"resource"})
        assert plan.context_parameters == ("context",)
        assert plan.protected_parameters == frozenset({"resource", "context"})
        described = describe_app(app, [plan], dependencies=registry).capabilities[0]
        assert [item.name for item in described.inputs] == ["value"]
        assert [item.parameter for item in described.dependencies] == ["resource"]
        container = DIContainer(registry)
        try:
            async with asyncio.timeout(5):
                for payload in (
                    {"value": "bad"},
                    {"value": 1, "receiver": "forged"},
                    {"value": 1, "context": "forged"},
                ):
                    result = await invoke_result(
                        plan,
                        ExecutionContext(
                            Invocation(plan.definition.id, payload, {}),
                            container,
                            principal=Principal("fixture", scopes={"read"}),
                        ),
                    )
                    assert isinstance(result, Failure) and result.code is FailureCode.INVALID_INPUT
                assert seed.events == []
                result = await invoke_result(
                    plan,
                    ExecutionContext(
                        Invocation(plan.definition.id, {"value": 7}, {}),
                        container,
                        principal=Principal("fixture", scopes={"read"}),
                    ),
                )
                assert result == Success(7)
        finally:
            await container.aclose()
        assert seed.events == [
            "seed.open",
            "resource.open",
            "handler",
            "resource.close",
            "seed.close",
        ]

    asyncio.run(run())


@pytest.mark.parametrize("seed_scope", [Scope.SINGLETON, Scope.INVOCATION])
def test_singleton_method_edges_include_only_actual_dependencies(seed_scope) -> None:
    async def run() -> None:
        seed = Seed()
        factory = MethodFactory()
        registry = registry_for(seed, seed_scope=seed_scope)
        registry.bind(Resource, provider(scope=Scope.SINGLETON)(factory.generate))
        app = Agnara("singleton_method")

        @app.capability(output=bool)
        def read(resource: Resource) -> bool:
            return resource.owner is factory and not resource.closed

        definition = app.compile()["singleton_method.read"]
        if seed_scope is Scope.INVOCATION:
            with pytest.raises(DefinitionError, match="invocation-scoped provider for Seed"):
                ExecutionPlan.compile(definition, registry)
            assert seed.events == []
            return
        plan = ExecutionPlan.compile(definition, registry)
        container = DIContainer(registry)
        try:
            async with asyncio.timeout(5):
                for _ in range(2):
                    assert await invoke_result(
                        plan, ExecutionContext(Invocation(definition.id, {}, {}), container)
                    ) == Success(True)
                assert len(seed.resources) == 1 and not seed.resources[0].closed
                assert seed.events == ["seed.open", "resource.open"]
        finally:
            await container.aclose()
        assert seed.events == ["seed.open", "resource.open", "resource.close", "seed.close"]

    asyncio.run(run())


def ordinary(self: int, cls: int) -> int:
    return self + cls


class OrdinaryParameters:
    @staticmethod
    def static(self: int, cls: int) -> int:
        return self + cls

    def unbound(self: OrdinaryParameters, value: int) -> int:
        assert isinstance(self, OrdinaryParameters)
        return value


@pytest.mark.parametrize("handler", [ordinary, OrdinaryParameters.static])
def test_ordinary_parameters_named_self_and_cls_remain_payload(handler) -> None:
    async def run() -> None:
        registry = DIRegistry()
        app = Agnara("normal_names")
        app.capability(name="add", output=int)(handler)
        plan = ExecutionPlan.compile(app.compile()["normal_names.add"], registry)
        assert list(plan.input_schemas) == ["self", "cls"]
        container = DIContainer(registry)
        try:
            assert await invoke_result(
                plan,
                ExecutionContext(
                    Invocation(plan.definition.id, {"self": 2, "cls": 3}, {}), container
                ),
            ) == Success(5)
        finally:
            await container.aclose()

    asyncio.run(run())


def test_unbound_receiver_remains_an_explicit_dependency() -> None:
    async def run() -> None:
        acquired = []

        @provider()
        def owner() -> OrdinaryParameters:
            acquired.append("owner")
            return OrdinaryParameters()

        registry = DIRegistry()
        registry.bind(OrdinaryParameters, owner)
        app = Agnara("unbound")
        app.capability(name="read", output=int)(OrdinaryParameters.unbound)
        plan = ExecutionPlan.compile(app.compile()["unbound.read"], registry)
        assert plan.dependency_parameters == frozenset({"self"})
        assert list(plan.input_schemas) == ["value"]
        assert acquired == []
        container = DIContainer(registry)
        try:
            assert await invoke_result(
                plan, ExecutionContext(Invocation(plan.definition.id, {"value": 7}, {}), container)
            ) == Success(7)
        finally:
            await container.aclose()
        assert acquired == ["owner"]

    asyncio.run(run())
