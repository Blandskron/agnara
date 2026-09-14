import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from agnara import InvocationError, PolicyDeniedError, ValidationError
from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIContainer, DIRegistry, provider
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    Success,
    classify_failure,
    invoke,
    invoke_result,
)
from agnara.policy import PolicyFailure, PolicyResult
from agnara.schema import TypeSchema


class Database:
    pass


@provider()
def provide_database() -> Database:
    return Database()


def definition(handler: Callable[..., Any], *, output: object = Any) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=CapabilityId("payments", "refund"),
        handler=handler,
        output=output,
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
    """A runtime-owned parameter is not an input, so naming one is unexpected input."""

    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Database, provide_database)

        def refund(database: Database, context: ExecutionContext) -> None:
            raise AssertionError("handler must not run")

        plan = ExecutionPlan.compile(definition(refund), registry)
        direct_context = context_for(plan, registry, {reserved_name: object()})

        with pytest.raises(ValidationError) as caught:
            await invoke(plan, direct_context)
        assert caught.value.message == "unexpected input"
        assert caught.value.path == (reserved_name,)

    asyncio.run(run_test())


def test_policies_run_before_a_runtime_owned_parameter_is_noticed() -> None:
    """An unauthorized caller must not learn dependency or context parameter
    names from the difference between "forbidden" and "unexpected input"."""

    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Database, provide_database)

        def refund(database: Database) -> None:
            raise AssertionError("handler must not run")

        plan = ExecutionPlan.compile(
            CapabilityDefinition.declare(
                id=CapabilityId("payments", "refund"),
                handler=refund,
                scopes={"payments:write"},
            ),
            registry,
        )
        probing = context_for(plan, registry, {"database": "forged"})

        with pytest.raises(PolicyDeniedError):
            await invoke(plan, probing)

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("payload", "path", "message"),
    [
        ({}, ("payment_id",), "required input is missing"),
        ({"payment_id": "pay_123", "extra": True}, ("extra",), "unexpected input"),
        ({"payment_id": 123}, ("payment_id",), "expected str, got int"),
    ],
)
def test_validates_payload_shape_and_values(
    payload: dict[str, Any], path: tuple[str, ...], message: str
) -> None:
    async def run_test() -> None:
        def refund(payment_id: str) -> None:
            raise AssertionError("handler must not run")

        registry = DIRegistry()
        plan = ExecutionPlan.compile(definition(refund), registry)

        with pytest.raises(ValidationError, match=message) as failure:
            await invoke(plan, context_for(plan, registry, payload))

        assert failure.value.path == path

    asyncio.run(run_test())


def test_omitted_optional_input_uses_handler_default() -> None:
    async def run_test() -> None:
        def refund(reason: str = "requested") -> str:
            return reason

        registry = DIRegistry()
        plan = ExecutionPlan.compile(definition(refund), registry)

        assert await invoke(plan, context_for(plan, registry)) == "requested"

    asyncio.run(run_test())


def test_passes_schema_return_value_without_mutating_invocation_payload() -> None:
    class IntegerFromText:
        def validate(self, value: object) -> int:
            if not isinstance(value, str):
                raise ValidationError("expected text")
            return int(value)

        def json_schema(self) -> dict[str, Any]:
            return {"type": "integer"}

    class Adapter:
        def compile(self, annotation: Any) -> TypeSchema:
            assert annotation is int
            return IntegerFromText()

        def supports(self, annotation: Any) -> bool:
            return annotation is int

    async def run_test() -> None:
        def refund(quantity: int) -> int:
            return quantity

        registry = DIRegistry()
        plan = ExecutionPlan.compile(definition(refund), registry, schema_adapter=Adapter())
        direct_context = context_for(plan, registry, {"quantity": "3"})

        assert await invoke(plan, direct_context) == 3
        assert direct_context.invocation.payload == {"quantity": "3"}

    asyncio.run(run_test())


def test_policy_denial_precedes_input_validation() -> None:
    class Deny:
        async def evaluate(self, context: ExecutionContext) -> PolicyResult:
            return PolicyFailure("not allowed")

    async def run_test() -> None:
        def refund(payment_id: str) -> None:
            raise AssertionError("handler must not run")

        registry = DIRegistry()
        capability = CapabilityDefinition(
            id=CapabilityId("payments", "refund"),
            handler=refund,
            policies=(Deny(),),
        )
        plan = ExecutionPlan.compile(capability, registry)

        with pytest.raises(PolicyDeniedError, match="not allowed"):
            await invoke(plan, context_for(plan, registry, {"payment_id": 123}))

    asyncio.run(run_test())


def test_invalid_input_does_not_construct_dependencies() -> None:
    async def run_test() -> None:
        constructed = False

        @provider()
        def tracked_database() -> Database:
            nonlocal constructed
            constructed = True
            return Database()

        def refund(payment_id: str, database: Database) -> None:
            raise AssertionError("handler must not run")

        registry = DIRegistry()
        registry.bind(Database, tracked_database)
        plan = ExecutionPlan.compile(definition(refund), registry)

        with pytest.raises(ValidationError):
            await invoke(plan, context_for(plan, registry, {"payment_id": 123}))
        assert constructed is False

    asyncio.run(run_test())


def test_canonical_invocation_maps_compiled_input_failure() -> None:
    async def run_test() -> None:
        def refund(payment_id: str) -> None:
            pass

        registry = DIRegistry()
        plan = ExecutionPlan.compile(definition(refund), registry)

        assert await invoke_result(
            plan, context_for(plan, registry, {"payment_id": 123})
        ) == Failure(
            FailureCode.INVALID_INPUT,
            "expected str, got int",
            details={"path": ("payment_id",)},
        )

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


def test_canonical_invocation_wraps_an_ordinary_success() -> None:
    async def run_test() -> None:
        registry = DIRegistry()
        plan = ExecutionPlan.compile(definition(lambda: "refunded"), registry)

        assert await invoke_result(plan, context_for(plan, registry)) == Success("refunded")

    asyncio.run(run_test())


def test_declared_unary_output_is_validated_before_a_success_is_returned() -> None:
    async def run_test() -> None:
        registry = DIRegistry()
        plan = ExecutionPlan.compile(definition(lambda: "refunded", output=str), registry)

        assert await invoke(plan, context_for(plan, registry)) == "refunded"
        assert await invoke_result(plan, context_for(plan, registry)) == Success("refunded")

    asyncio.run(run_test())


def test_invalid_declared_unary_output_is_redacted_as_an_internal_failure() -> None:
    async def run_test() -> None:
        registry = DIRegistry()
        plan = ExecutionPlan.compile(definition(lambda: "secret refund data", output=int), registry)

        with pytest.raises(InvocationError, match="does not satisfy its declared output"):
            await invoke(plan, context_for(plan, registry))

        outcome = await invoke_result(plan, context_for(plan, registry))
        assert outcome == Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")

    asyncio.run(run_test())


def test_canonical_invocation_preserves_an_explicit_failure() -> None:
    async def run_test() -> None:
        registry = DIRegistry()
        expected = Failure(FailureCode.CONFLICT, "payment was already refunded")
        plan = ExecutionPlan.compile(definition(lambda: expected, output=str), registry)

        context = context_for(plan, registry)
        outcome = await invoke_result(plan, context)

        assert outcome == expected
        assert outcome is not expected
        assert outcome.execution_id == context.execution_id

    asyncio.run(run_test())


def test_canonical_invocation_maps_validation_with_immutable_path() -> None:
    async def run_test() -> None:
        registry = DIRegistry()

        def refund() -> None:
            raise ValidationError("expected a string", path=("payment", "id"))

        plan = ExecutionPlan.compile(definition(refund), registry)

        assert await invoke_result(plan, context_for(plan, registry)) == Failure(
            FailureCode.INVALID_INPUT,
            "expected a string",
            {"path": ("payment", "id")},
        )

    asyncio.run(run_test())


def test_canonical_invocation_redacts_unexpected_handler_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Neither the caller nor default logs receive exception-carried secrets."""

    async def run_test() -> None:
        registry = DIRegistry()

        def refund() -> None:
            raise RuntimeError("database password is secret")

        plan = ExecutionPlan.compile(definition(refund), registry)
        with caplog.at_level(logging.ERROR, logger="agnara.execution"):
            outcome = await invoke_result(plan, context_for(plan, registry))

        assert outcome == Failure(
            FailureCode.INTERNAL_FAILURE,
            "capability invocation failed",
        )
        assert isinstance(outcome, Failure)
        assert "secret" not in outcome.message

        [record] = caplog.records
        assert record.name == "agnara.execution"
        assert record.levelno == logging.ERROR
        assert record.getMessage() == "capability payments.refund failed"
        assert "database password" not in caplog.text
        assert "RuntimeError" not in caplog.text
        assert record.exc_info is None

    asyncio.run(run_test())


def test_canonical_invocation_maps_expired_deadline() -> None:
    async def run_test() -> None:
        registry = DIRegistry()

        async def refund() -> None:
            await asyncio.Event().wait()

        plan = ExecutionPlan.compile(definition(refund), registry)
        deadline = asyncio.get_running_loop().time()

        assert await invoke_result(
            plan,
            context_for(plan, registry, deadline=deadline),
        ) == Failure(FailureCode.TIMEOUT, "invocation deadline exceeded")

    asyncio.run(run_test())


def test_canonical_invocation_propagates_external_cancellation() -> None:
    async def run_test() -> None:
        registry = DIRegistry()
        started = asyncio.Event()

        async def refund() -> None:
            started.set()
            await asyncio.Event().wait()

        plan = ExecutionPlan.compile(definition(refund), registry)
        task = asyncio.create_task(invoke_result(plan, context_for(plan, registry)))
        await started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# The published classifier an adapter owning its own boundary needs
# ---------------------------------------------------------------------------


class TestClassifyFailure:
    """ADR 0085: one exception-to-`Failure` rule, published rather than copied.

    `open_stream` raises an ordinary exception for a pre-output failure, so an
    adapter that owns a streaming wire has to classify it itself. These cases
    prove it gets the same answer `invoke_result` would have given, which is
    the only reason exporting the rule is safer than letting each transport
    write its own.
    """

    def test_a_known_runtime_error_keeps_its_semantic_category(self) -> None:
        assert classify_failure(
            PolicyDeniedError("no viewer may refund"), CapabilityId("payments", "refund")
        ) == Failure(FailureCode.FORBIDDEN, "no viewer may refund")

    def test_an_expired_deadline_is_a_timeout(self) -> None:
        assert classify_failure(TimeoutError(), CapabilityId("payments", "refund")) == Failure(
            FailureCode.TIMEOUT, "invocation deadline exceeded"
        )

    def test_an_unexpected_exception_is_redacted(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.ERROR, logger="agnara.execution"):
            failure = classify_failure(
                RuntimeError("database password is secret"),
                CapabilityId("payments", "refund"),
            )

        assert failure == Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")
        assert "secret" not in failure.message
        assert "database password" not in caplog.text
        [record] = caplog.records
        assert record.getMessage() == "capability payments.refund failed"
        assert record.exc_info is None

    def test_it_answers_exactly_as_the_complete_result_boundary_does(self) -> None:
        """The point of the export: two boundaries, one redaction decision."""

        async def run_test() -> None:
            registry = DIRegistry()

            def refund() -> None:
                raise RuntimeError("database password is secret")

            plan = ExecutionPlan.compile(definition(refund), registry)
            outcome = await invoke_result(plan, context_for(plan, registry))

            assert outcome == classify_failure(
                RuntimeError("database password is secret"), plan.definition.id
            )

        asyncio.run(run_test())

    @pytest.mark.parametrize(
        ("error", "capability_id", "message"),
        [
            ("not an exception", CapabilityId("payments", "refund"), "error must be an Exception"),
            (RuntimeError("boom"), "payments.refund", "capability_id must be a CapabilityId"),
        ],
    )
    def test_it_refuses_arguments_of_the_wrong_type(
        self, error: Any, capability_id: Any, message: str
    ) -> None:
        with pytest.raises(TypeError, match=message):
            classify_failure(error, capability_id)
