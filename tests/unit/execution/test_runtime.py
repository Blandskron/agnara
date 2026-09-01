import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from agnara import InvocationError
from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIContainer, DIRegistry, provider
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation, invoke


class Database:
    pass


@provider()
def provide_database() -> Database:
    return Database()


def definition(handler: Callable[..., Any]) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=CapabilityId("payments", "refund"),
        handler=handler,
    )


def context_for(
    plan: ExecutionPlan,
    registry: DIRegistry,
    payload: dict[str, Any] | None = None,
    *,
    capability_id: CapabilityId | None = None,
    deadline: float | None = None,
) -> ExecutionContext:
    invocation = Invocation(
        capability_id=capability_id or plan.definition.id,
        payload=payload or {},
        metadata={},
        deadline=deadline,
    )
    return ExecutionContext(invocation, DIContainer(registry))


def test_invokes_sync_handler_with_payload_and_dependency() -> None:
    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Database, provide_database)

        def refund(payment_id: str, database: Database) -> tuple[str, Database]:
            return payment_id, database

        plan = ExecutionPlan.compile(definition(refund), registry)
        context = context_for(plan, registry, {"payment_id": "pay_123"})

        payment_id, database = await invoke(plan, context)

        assert payment_id == "pay_123"
        assert isinstance(database, Database)
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_invokes_async_handler_and_injects_execution_context() -> None:
    async def run_test() -> None:
        registry = DIRegistry()

        async def refund(payment_id: str, context: ExecutionContext) -> str:
            await asyncio.sleep(0)
            return f"{payment_id}:{context.tracking_id}"

        plan = ExecutionPlan.compile(definition(refund), registry)
        context = context_for(plan, registry, {"payment_id": "pay_123"})
        context.tracking_id = "trace_456"

        assert await invoke(plan, context) == "pay_123:trace_456"

    asyncio.run(run_test())


def test_awaits_value_returned_dynamically_by_sync_handler() -> None:
    async def run_test() -> None:
        registry = DIRegistry()

        async def completed() -> str:
            return "refunded"

        def refund() -> Any:
            return completed()

        plan = ExecutionPlan.compile(definition(refund), registry)

        assert await invoke(plan, context_for(plan, registry)) == "refunded"

    asyncio.run(run_test())


def test_rejects_invocation_for_another_capability() -> None:
    async def run_test() -> None:
        registry = DIRegistry()
        plan = ExecutionPlan.compile(definition(lambda: None), registry)
        context = context_for(
            plan,
            registry,
            capability_id=CapabilityId("payments", "capture"),
        )

        with pytest.raises(InvocationError, match=r"compiled plan is for payments\.refund"):
            await invoke(plan, context)

    asyncio.run(run_test())


@pytest.mark.parametrize("reserved_name", ["database", "context"])
def test_rejects_payload_values_for_runtime_owned_parameters(reserved_name: str) -> None:
    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Database, provide_database)

        def refund(database: Database, context: ExecutionContext) -> None:
            pass

        plan = ExecutionPlan.compile(definition(refund), registry)
        direct_context = context_for(plan, registry, {reserved_name: object()})

        with pytest.raises(InvocationError, match=reserved_name):
            await invoke(plan, direct_context)

    asyncio.run(run_test())


def test_cleans_up_invocation_resource_when_handler_raises() -> None:
    async def run_test() -> None:
        events: list[str] = []

        class Resource:
            pass

        @provider()
        async def provide_resource() -> AsyncIterator[Resource]:
            events.append("opened")
            try:
                yield Resource()
            finally:
                events.append("closed")

        registry = DIRegistry()
        registry.bind(Resource, provide_resource)

        async def refund(resource: Resource) -> None:
            assert isinstance(resource, Resource)
            raise RuntimeError("handler failed")

        plan = ExecutionPlan.compile(definition(refund), registry)

        with pytest.raises(RuntimeError, match="handler failed"):
            await invoke(plan, context_for(plan, registry))

        assert events == ["opened", "closed"]

    asyncio.run(run_test())


def test_handler_cancellation_propagates_and_cleans_up_resource() -> None:
    async def run_test() -> None:
        events: list[str] = []
        handler_started = asyncio.Event()
        never_complete = asyncio.Event()

        class Resource:
            pass

        @provider()
        async def provide_resource() -> AsyncIterator[Resource]:
            events.append("opened")
            try:
                yield Resource()
            finally:
                events.append("closed")

        registry = DIRegistry()
        registry.bind(Resource, provide_resource)

        async def refund(resource: Resource) -> None:
            assert isinstance(resource, Resource)
            handler_started.set()
            await never_complete.wait()

        plan = ExecutionPlan.compile(definition(refund), registry)
        direct_context = context_for(
            plan,
            registry,
            deadline=asyncio.get_running_loop().time() + 3600.0,
        )
        invocation_task = asyncio.create_task(invoke(plan, direct_context))
        await handler_started.wait()

        invocation_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await invocation_task
        assert events == ["opened", "closed"]

    asyncio.run(run_test())


def test_expired_deadline_times_out_handler_and_cleans_up_resource() -> None:
    async def run_test() -> None:
        events: list[str] = []

        class Resource:
            pass

        @provider()
        async def provide_resource() -> AsyncIterator[Resource]:
            events.append("opened")
            try:
                yield Resource()
            finally:
                events.append("closed")

        registry = DIRegistry()
        registry.bind(Resource, provide_resource)

        async def refund(resource: Resource) -> None:
            assert isinstance(resource, Resource)
            await asyncio.Event().wait()

        plan = ExecutionPlan.compile(definition(refund), registry)
        deadline = asyncio.get_running_loop().time()

        with pytest.raises(TimeoutError):
            await invoke(plan, context_for(plan, registry, deadline=deadline))
        assert events == ["opened", "closed"]

    asyncio.run(run_test())


def test_expired_deadline_times_out_dependency_construction_and_cleans_up() -> None:
    async def run_test() -> None:
        events: list[str] = []

        class Resource:
            pass

        class Service:
            pass

        @provider()
        def provide_resource() -> Resource:
            events.append("created")
            return Resource()

        @provider()
        async def provide_service(resource: Resource) -> AsyncIterator[Service]:
            assert isinstance(resource, Resource)
            try:
                await asyncio.Event().wait()
                yield Service()
            finally:
                events.append("cancelled")

        registry = DIRegistry()
        registry.bind(Resource, provide_resource)
        registry.bind(Service, provide_service)

        async def refund(service: Service) -> None:
            raise AssertionError("handler must not run")

        plan = ExecutionPlan.compile(definition(refund), registry)
        deadline = asyncio.get_running_loop().time()

        with pytest.raises(TimeoutError):
            await invoke(plan, context_for(plan, registry, deadline=deadline))
        assert events == ["created", "cancelled"]

    asyncio.run(run_test())


def test_dependency_construction_cancellation_cleans_up_entered_resource() -> None:
    async def run_test() -> None:
        events: list[str] = []
        dependency_started = asyncio.Event()
        never_complete = asyncio.Event()

        class Resource:
            pass

        class Service:
            pass

        @provider()
        async def provide_resource() -> AsyncIterator[Resource]:
            events.append("opened")
            try:
                yield Resource()
            finally:
                events.append("closed")

        @provider()
        async def provide_service(resource: Resource) -> AsyncIterator[Service]:
            assert isinstance(resource, Resource)
            dependency_started.set()
            await never_complete.wait()
            yield Service()

        registry = DIRegistry()
        registry.bind(Resource, provide_resource)
        registry.bind(Service, provide_service)

        async def refund(service: Service) -> None:
            raise AssertionError("handler must not run")

        plan = ExecutionPlan.compile(definition(refund), registry)
        invocation_task = asyncio.create_task(invoke(plan, context_for(plan, registry)))
        await dependency_started.wait()

        invocation_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await invocation_task
        assert events == ["opened", "closed"]

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("plan", "context", "message"),
    [
        (object(), object(), "plan must be an ExecutionPlan"),
        (
            ExecutionPlan.compile(definition(lambda: None), DIRegistry()),
            object(),
            "context must be an ExecutionContext",
        ),
    ],
)
def test_rejects_invalid_runtime_inputs(plan: object, context: object, message: str) -> None:
    async def run_test() -> None:
        with pytest.raises(TypeError, match=message):
            await invoke(plan, context)  # type: ignore

    asyncio.run(run_test())
