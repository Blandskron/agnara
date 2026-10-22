"""Handler calling conventions apply to payload and injected parameters alike."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId, CapabilityRegistry
from agnara.core.di import DIContainer, DIRegistry, provider
from agnara.errors import DefinitionError
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
)


class Database:
    pass


@pytest.mark.parametrize("annotation", [str, Database, ExecutionContext, CapabilityInvoker])
@pytest.mark.parametrize(
    "signature", ["resource: Injected, /", "*resource: Injected", "**resource: Injected"]
)
@pytest.mark.parametrize("direct", [False, True])
def test_invalid_handler_parameter_shapes_fail_at_startup(annotation, signature, direct):
    effects = []

    @provider()
    def database() -> Database:
        effects.append("provider")
        return Database()

    namespace: dict[str, Any] = {"Injected": annotation, "effects": effects}
    exec(f"def handler({signature}) -> None:\n    effects.append('handler')\n", namespace)
    handler = namespace["handler"]
    definition = CapabilityDefinition(id=CapabilityId.parse("signatures.invalid"), handler=handler)
    registry = DIRegistry()
    registry.bind(Database, database)

    with pytest.raises(
        DefinitionError,
        match=r"signatures\.invalid.*resource.*positional-or-keyword or keyword-only",
    ):
        if direct:
            dependencies = (Database,) if annotation is Database else ()
            ExecutionPlan(definition, {handler: dependencies})
        else:
            ExecutionPlan.compile(definition, registry)
    assert effects == []


@pytest.mark.parametrize("keyword_only", [False, True])
def test_named_handler_parameters_preserve_injection_and_nested_calls(keyword_only):
    async def run() -> None:
        events = []
        resource = Database()

        @provider()
        def database_provider() -> Iterator[Database]:
            events.append("open")
            try:
                yield resource
            finally:
                events.append("close")

        child_id = CapabilityId.parse("signatures.child")

        def child(value: str) -> str:
            events.append("child")
            return value + "!"

        async def call(value, database, context, invoker):
            assert database is resource
            assert context is expected_context
            assert isinstance(invoker, CapabilityInvoker)
            events.append("parent")
            outcome = await invoker.invoke(child_id, {"value": value})
            assert isinstance(outcome, Success)
            return outcome.value

        namespace: dict[str, Any] = {
            "Database": Database,
            "ExecutionContext": ExecutionContext,
            "CapabilityInvoker": CapabilityInvoker,
            "call": call,
        }
        prefix = "*, " if keyword_only else ""
        exec(
            f"async def handler({prefix}value: str, database: Database, "
            "context: ExecutionContext, invoker: CapabilityInvoker) -> str:\n"
            "    return await call(value, database, context, invoker)\n",
            namespace,
        )
        definition = CapabilityDefinition(
            id=CapabilityId.parse("signatures.parent"), handler=namespace["handler"], output=str
        )
        child_definition = CapabilityDefinition(id=child_id, handler=child, output=str)
        registry = DIRegistry()
        registry.bind(Database, database_provider)
        parent_plan = ExecutionPlan.compile(definition, registry)
        child_plan = ExecutionPlan.compile(child_definition, registry)
        assert tuple(parent_plan.input_schemas) == ("value",)
        assert parent_plan.protected_parameters == {"database", "context", "invoker"}
        assert events == []

        container = DIContainer(registry)
        runtime = CapabilityRuntime(
            CapabilityRegistry([definition, child_definition]).freeze(),
            [parent_plan, child_plan],
            container,
        )
        expected_context = ExecutionContext(
            Invocation(definition.id, {"value": "ok"}, {}), container
        )
        try:
            result = await runtime.invoke_result(expected_context)
            assert isinstance(result, Success)
            assert result.value == "ok!"
            assert events == ["open", "parent", "child", "close"]
        finally:
            await runtime.aclose()

    asyncio.run(run())
