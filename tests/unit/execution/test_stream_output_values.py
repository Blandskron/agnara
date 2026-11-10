"""Stream units are values; canonical outcomes belong to complete results."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest

from agnara import Agnara
from agnara.di import DIContainer, DIRegistry, provider
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    StreamInterrupted,
    StreamTerminal,
    Success,
    invoke_result,
    open_stream,
)
from agnara.schema import TypeSchema

VALUES = [
    Success(1, execution_id="original-execution"),
    Failure(FailureCode.CONFLICT, "private failure marker", execution_id="original-execution"),
]


class Resource:
    pass


@pytest.mark.parametrize("unit", VALUES)
@pytest.mark.parametrize("prefix", [False, True])
def test_result_objects_cannot_bypass_a_stream_unit_schema(unit, prefix):
    async def run():
        events = []

        @provider()
        def resource() -> Iterator[Resource]:
            events.append("resource.open")
            try:
                yield Resource()
            finally:
                events.append("resource.close")

        app = Agnara("streams")

        @app.capability(streaming=True, output=int)
        async def rows(resource: Resource) -> AsyncIterator[object]:
            try:
                if prefix:
                    yield 1
                yield unit
            finally:
                events.append("producer.close")

        registry = DIRegistry()
        registry.bind(Resource, resource)
        definition = app.compile()["streams.rows"]
        plan = ExecutionPlan.compile(definition, registry)
        container = DIContainer(registry)
        try:
            context = ExecutionContext(Invocation(definition.id, {}, {}), container)
            async with open_stream(plan, context) as stream:
                if prefix:
                    assert await anext(stream) == 1
                with pytest.raises(StreamInterrupted) as caught:
                    await anext(stream)
                assert stream.terminal is StreamTerminal.INTERRUPTED
                assert stream.units_emitted == int(prefix)
                assert caught.value.units_emitted == int(prefix)
                assert caught.value.failure.code is FailureCode.INTERNAL_FAILURE
                assert caught.value.failure.message == "capability invocation failed"
                assert "private failure marker" not in repr(caught.value.failure)
            assert events == ["resource.open", "producer.close", "resource.close"]
        finally:
            await container.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("unit", VALUES)
@pytest.mark.parametrize("custom", [False, True])
def test_admitted_result_objects_are_validated_as_actual_data(unit, custom):
    async def run():
        observed = []

        class UnitSchema:
            def validate(self, value: object) -> Any:
                observed.append(value)
                assert value is unit
                return 99

            def json_schema(self):
                return {"type": "integer"}

        class Adapter:
            def compile(self, annotation: object) -> TypeSchema:
                return UnitSchema()

            def supports(self, annotation: object) -> bool:
                return True

        app = Agnara("streams")

        @app.capability(streaming=True, output=int if custom else Any)
        async def rows() -> AsyncIterator[object]:
            yield unit

        registry = DIRegistry()
        definition = app.compile()["streams.rows"]
        plan = ExecutionPlan.compile(
            definition, registry, schema_adapter=Adapter() if custom else None
        )
        container = DIContainer(registry)
        try:
            context = ExecutionContext(Invocation(definition.id, {}, {}), container)
            async with open_stream(plan, context) as stream:
                value = await anext(stream)
                if custom:
                    assert value == 99
                    assert len(observed) == 1 and observed[0] is unit
                else:
                    assert value is unit
                    assert value.execution_id == "original-execution"
                with pytest.raises(StopAsyncIteration):
                    await anext(stream)
                assert stream.terminal is StreamTerminal.COMPLETED
                assert stream.units_emitted == 1
        finally:
            await container.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("outcome", VALUES)
def test_complete_result_outcomes_retain_their_existing_semantics(outcome):
    async def run():
        app = Agnara("streams")

        @app.capability(output=int)
        def complete() -> object:
            return outcome

        registry = DIRegistry()
        definition = app.compile()["streams.complete"]
        plan = ExecutionPlan.compile(definition, registry)
        container = DIContainer(registry)
        try:
            context = ExecutionContext(Invocation(definition.id, {}, {}), container)
            assert await invoke_result(plan, context) == outcome
        finally:
            await container.aclose()

    asyncio.run(run())
