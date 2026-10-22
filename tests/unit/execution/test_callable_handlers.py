"""Callable instances keep their call-method contracts through compilation."""

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest

from agnara import Agnara, DefinitionError
from agnara.di import DIContainer, DIRegistry, provider
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    Success,
    invoke_result,
    open_stream,
)
from agnara.introspection import describe_app


class Database:
    pass


class SyncHandler:
    def __init__(self, events: list[str]):
        self.events = events

    def __call__(
        self: SyncHandler, value: int, database: Database, context: ExecutionContext
    ) -> int:
        assert isinstance(database, Database)
        assert context.invocation.payload["value"] == value
        self.events.append("handler")
        return value + 1


class AsyncHandler:
    def __init__(self, events: list[str]):
        self.sync = SyncHandler(events)

    async def __call__(self, value: int, database: Database, context: ExecutionContext) -> int:
        await asyncio.sleep(0)
        return self.sync(value, database, context)


@pytest.mark.parametrize("kind", ["sync_instance", "async_instance", "bound_method", "function"])
def test_callable_contract_survives_registration_execution_and_introspection(kind):
    async def run():
        events = []

        @provider()
        def database() -> Iterator[Database]:
            events.append("open")
            try:
                yield Database()
            finally:
                events.append("close")

        sync = SyncHandler(events)

        def function(value: int, database: Database, context: ExecutionContext) -> int:
            return sync(value, database, context)

        handler = {
            "sync_instance": sync,
            "async_instance": AsyncHandler(events),
            "bound_method": sync.__call__,
            "function": function,
        }[kind]
        app = Agnara("callables")
        app.capability(name="increment", output=int)(handler)
        definition = app.compile()["callables.increment"]
        registry = DIRegistry()
        registry.bind(Database, database)
        if kind == "sync_instance":

            @provider()
            def receiver() -> SyncHandler:
                raise AssertionError("the bound receiver must not become a dependency")

            registry.bind(SyncHandler, receiver)
        plan = ExecutionPlan.compile(definition, registry)
        described = describe_app(app, [plan], dependencies=registry).capabilities[0]
        assert [item.name for item in described.inputs] == ["value"]
        assert [item.parameter for item in described.dependencies] == ["database"]
        assert plan.context_parameters == ("context",)
        assert events == []

        container = DIContainer(registry)
        try:
            context = ExecutionContext(Invocation(definition.id, {"value": 3}, {}), container)
            result = await invoke_result(plan, context)
            assert isinstance(result, Success)
            assert result.value == 4
            assert events == ["open", "handler", "close"]
        finally:
            await container.aclose()

    asyncio.run(run())


def test_callable_input_and_output_validation_preserve_effect_boundaries():
    async def run():
        events = []

        @provider()
        def database() -> Iterator[Database]:
            events.append("open")
            try:
                yield Database()
            finally:
                events.append("close")

        class InvalidProducer:
            def __call__(self, value: int, database: Database) -> str:
                events.append("handler")
                return "private output"

        app = Agnara("callables")
        app.capability(name="invalid", output=int)(InvalidProducer())
        definition = app.compile()["callables.invalid"]
        registry = DIRegistry()
        registry.bind(Database, database)
        plan = ExecutionPlan.compile(definition, registry)
        container = DIContainer(registry)
        try:
            invalid = ExecutionContext(Invocation(definition.id, {"value": "wrong"}, {}), container)
            rejected = await invoke_result(plan, invalid)
            assert isinstance(rejected, Failure)
            assert rejected.code is FailureCode.INVALID_INPUT
            assert events == []
            valid = ExecutionContext(Invocation(definition.id, {"value": 3}, {}), container)
            failed = await invoke_result(plan, valid)
            assert isinstance(failed, Failure)
            assert failed.code is FailureCode.INTERNAL_FAILURE
            assert "private output" not in repr(failed)
            assert events == ["open", "handler", "close"]
        finally:
            await container.aclose()

    asyncio.run(run())


def test_callable_positional_context_is_refused_before_execution():
    class InvalidShape:
        def __call__(self, context: ExecutionContext, /) -> None:
            raise AssertionError("must not execute")

    app = Agnara("callables")
    app.capability(name="invalid")(InvalidShape())
    with pytest.raises(DefinitionError, match="positional-or-keyword or keyword-only"):
        ExecutionPlan.compile(app.compile()["callables.invalid"], DIRegistry())


def test_callable_unresolved_annotations_fail_at_startup():
    class Broken:
        def __call__(self, value):
            raise AssertionError("must not execute")

    Broken.__call__.__annotations__ = {"value": "NeverDefined", "return": int}
    app = Agnara("callables")
    app.capability(name="broken")(Broken())
    with pytest.raises(DefinitionError, match="NeverDefined"):
        ExecutionPlan.compile(app.compile()["callables.broken"], DIRegistry())


@pytest.mark.parametrize("streaming", [False, True])
def test_callable_async_generator_keeps_explicit_stream_declaration(streaming):
    class Rows:
        async def __call__(self, count: int) -> AsyncIterator[int]:
            for index in range(count):
                yield index

    app = Agnara("callables")
    app.capability(name="rows", streaming=streaming, output=int)(Rows())
    definition = app.compile()["callables.rows"]
    registry = DIRegistry()
    if not streaming:
        with pytest.raises(DefinitionError, match="does not declare"):
            ExecutionPlan.compile(definition, registry)
        return
    plan = ExecutionPlan.compile(definition, registry)

    async def run():
        container = DIContainer(registry)
        try:
            context = ExecutionContext(Invocation(definition.id, {"count": 2}, {}), container)
            async with open_stream(plan, context) as stream:
                assert [item async for item in stream] == [0, 1]
        finally:
            await container.aclose()

    asyncio.run(run())
