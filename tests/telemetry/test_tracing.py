"""E9.3 real SDK evidence for the capability span bridge."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextvars import copy_context
from typing import Any
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import (
    INVALID_SPAN,
    NoOpTracerProvider,
    StatusCode,
    get_current_span,
    get_tracer_provider,
)

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    InvocationStartEvent,
    InvocationTerminalEvent,
    invoke,
)
from agnara_telemetry import OpenTelemetryMetricsHook, OpenTelemetryTracingHook

CAPABILITY = CapabilityId.parse("tests.traced")
INNER = CapabilityId.parse("tests.inner")

#: Every value the runtime is given that must never reach an exporter.
SECRET_TRACKING_ID = "tracking-id-must-not-export"
SECRET_METADATA = "metadata-must-not-export"
SECRET_FAILURE_TEXT = "exception-text-must-not-export"


@pytest.fixture
def traced() -> Iterator[tuple[OpenTelemetryTracingHook, InMemorySpanExporter]]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        yield OpenTelemetryTracingHook(provider.get_tracer("agnara_telemetry")), exporter
    finally:
        provider.shutdown()


def start(invocation_id: str, capability: CapabilityId = CAPABILITY) -> InvocationStartEvent:
    return InvocationStartEvent(capability, SECRET_TRACKING_ID, invocation_id)


def terminal(
    invocation_id: str,
    outcome: str,
    capability: CapabilityId = CAPABILITY,
) -> InvocationTerminalEvent:
    return InvocationTerminalEvent(capability, SECRET_TRACKING_ID, 1_000, outcome, invocation_id)


def plan_for(
    hooks: list[Any],
    handler: Any,
    registry: DIRegistry,
    capability: CapabilityId = CAPABILITY,
) -> ExecutionPlan:
    definition = CapabilityDefinition.declare(id=capability, handler=handler)
    return ExecutionPlan.compile(definition, registry, hooks=hooks)


def context_for(
    plan: ExecutionPlan,
    registry: DIRegistry,
    deadline: float | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        Invocation(
            capability_id=plan.definition.id,
            payload={},
            metadata={"tracking_id": SECRET_TRACKING_ID, "secret": SECRET_METADATA},
            deadline=deadline,
        ),
        DIContainer(registry),
    )


def exported(exporter: InMemorySpanExporter) -> tuple[ReadableSpan, ...]:
    return exporter.get_finished_spans()


def outcome_of(span: ReadableSpan) -> Any:
    assert span.attributes is not None
    return span.attributes["agnara.invocation.outcome"]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "supplied", [None, object(), "tracer", TracerProvider(shutdown_on_exit=False)]
)
def test_construction_requires_a_real_tracer(supplied: Any) -> None:
    """A provider is not a tracer; accepting one would hide a wiring mistake."""
    with pytest.raises(TypeError, match="tracer must be an OpenTelemetry Tracer"):
        OpenTelemetryTracingHook(supplied)


def test_construction_never_reads_or_installs_a_global_provider() -> None:
    before = get_tracer_provider()
    provider = TracerProvider(shutdown_on_exit=False)
    try:
        OpenTelemetryTracingHook(provider.get_tracer("agnara_telemetry"))
        assert get_tracer_provider() is before
    finally:
        provider.shutdown()


def test_the_api_only_no_op_tracer_records_nothing_and_raises_nothing() -> None:
    """An application that never configures an SDK must still be able to run."""
    hook = OpenTelemetryTracingHook(NoOpTracerProvider().get_tracer("agnara_telemetry"))
    identity = uuid4().hex
    hook.on_invocation_start(start(identity))
    hook.on_invocation_terminal(terminal(identity, "success"))


# ---------------------------------------------------------------------------
# One span per invocation
# ---------------------------------------------------------------------------


def test_a_span_is_produced_only_once_the_invocation_terminates(traced: Any) -> None:
    hook, exporter = traced
    identity = uuid4().hex

    hook.on_invocation_start(start(identity))
    assert exported(exporter) == ()

    hook.on_invocation_terminal(terminal(identity, "success"))
    assert len(exported(exporter)) == 1


@pytest.mark.parametrize(
    ("outcome", "recorded", "status"),
    [
        ("success", "success", StatusCode.OK),
        ("failure", "failure", StatusCode.ERROR),
        ("timeout", "timeout", StatusCode.ERROR),
        ("cancellation", "cancellation", StatusCode.UNSET),
        ("not-an-outcome", "unknown", StatusCode.UNSET),
        ("", "unknown", StatusCode.UNSET),
    ],
)
def test_outcome_attribute_and_status_are_a_closed_vocabulary(
    traced: Any,
    outcome: str,
    recorded: str,
    status: StatusCode,
) -> None:
    """An unrecognized direct event must not create an unbounded attribute."""
    hook, exporter = traced
    identity = uuid4().hex

    hook.on_invocation_start(start(identity))
    hook.on_invocation_terminal(terminal(identity, outcome))

    (span,) = exported(exporter)
    assert span.name == str(CAPABILITY)
    assert span.attributes is not None
    expected = {
        "agnara.capability.id": str(CAPABILITY),
        "agnara.invocation.outcome": recorded,
    }
    if status is StatusCode.ERROR:
        # ADR 0057: the one stable convention attribute Agnara adopts, carrying
        # the same closed vocabulary rather than an exception type.
        expected["error.type"] = recorded
    assert dict(span.attributes) == expected
    assert span.status.status_code is status
    assert span.status.description in (None, recorded if status is StatusCode.ERROR else None)


def test_a_terminal_event_without_a_start_is_ignored(traced: Any) -> None:
    """The runtime suppresses a failing start callback; the pair still arrives."""
    hook, exporter = traced

    hook.on_invocation_terminal(terminal(uuid4().hex, "success"))

    assert exported(exporter) == ()


def test_a_repeated_terminal_event_does_not_end_a_span_twice(traced: Any) -> None:
    hook, exporter = traced
    identity = uuid4().hex

    hook.on_invocation_start(start(identity))
    hook.on_invocation_terminal(terminal(identity, "success"))
    hook.on_invocation_terminal(terminal(identity, "failure"))

    (span,) = exported(exporter)
    assert span.attributes is not None
    assert span.attributes["agnara.invocation.outcome"] == "success"


def test_repeated_tracking_ids_do_not_merge_distinct_invocations(traced: Any) -> None:
    """Every event here carries one shared tracking ID on purpose."""
    hook, exporter = traced
    first, second = uuid4().hex, uuid4().hex

    hook.on_invocation_start(start(first))
    hook.on_invocation_start(start(second))
    hook.on_invocation_terminal(terminal(second, "failure"))
    hook.on_invocation_terminal(terminal(first, "success"))

    spans = exported(exporter)
    assert [outcome_of(span) for span in spans] == ["failure", "success"]
    assert len({span.context.span_id for span in spans}) == 2


def test_out_of_order_delivery_still_ends_every_span(traced: Any) -> None:
    """Pins the boundary of the attach/detach design, rather than claiming none.

    The runtime brackets a start and its terminal inside one task, so context
    tokens are always released in reverse order. Events delivered directly and
    out of order are outside that guarantee: every span still ends and exports,
    but OpenTelemetry drops an out-of-order detach and the previous span is not
    restored. That is why this runs in an isolated context: the damage is real
    enough to leak into unrelated work. Do not hand-deliver interleaved events.
    """
    hook, exporter = traced
    first, second = uuid4().hex, uuid4().hex

    def deliver_out_of_order() -> Any:
        hook.on_invocation_start(start(first))
        hook.on_invocation_start(start(second))
        hook.on_invocation_terminal(terminal(first, "success"))
        hook.on_invocation_terminal(terminal(second, "success"))
        return get_current_span()

    stranded = copy_context().run(deliver_out_of_order)

    assert len(exported(exporter)) == 2
    assert hook._spans == {}
    # Every span was ended; what was lost is the context, not the telemetry.
    assert not stranded.is_recording()
    assert get_current_span() is INVALID_SPAN


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_no_caller_or_runtime_payload_reaches_the_exporter(traced: Any) -> None:
    hook, exporter = traced
    registry = DIRegistry()

    def handler() -> str:
        raise ValueError(SECRET_FAILURE_TEXT)

    plan = plan_for([hook], handler, registry)
    with pytest.raises(ValueError):
        asyncio.run(invoke(plan, context_for(plan, registry)))

    (span,) = exported(exporter)
    rendered = repr(span.to_json())
    for secret in (SECRET_TRACKING_ID, SECRET_METADATA, SECRET_FAILURE_TEXT):
        assert secret not in rendered
    assert span.events == ()
    assert span.attributes is not None
    assert set(span.attributes) == {
        "agnara.capability.id",
        "agnara.invocation.outcome",
        "error.type",
    }
    assert span.attributes["error.type"] == "failure"


def test_an_invocation_identity_is_not_exported_as_an_attribute(traced: Any) -> None:
    """It pairs events in-process; as an attribute it is unbounded cardinality."""
    hook, exporter = traced
    identity = uuid4().hex

    hook.on_invocation_start(start(identity))
    hook.on_invocation_terminal(terminal(identity, "success"))

    (span,) = exported(exporter)
    assert identity not in span.to_json()


# ---------------------------------------------------------------------------
# Runtime integration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", ["success", "failure", "timeout", "cancellation"])
def test_the_runtime_produces_one_span_per_outcome(traced: Any, outcome: str) -> None:
    hook, exporter = traced
    registry = DIRegistry()

    async def handler() -> str:
        if outcome == "failure":
            raise ValueError(SECRET_FAILURE_TEXT)
        if outcome == "timeout":
            await asyncio.sleep(60)
        if outcome == "cancellation":
            raise asyncio.CancelledError
        return "ok"

    async def run() -> None:
        plan = plan_for([hook], handler, registry)
        deadline = None
        if outcome == "timeout":
            deadline = asyncio.get_running_loop().time() + 0.01
        context = context_for(plan, registry, deadline=deadline)
        if outcome == "success":
            assert await invoke(plan, context) == "ok"
            return
        with pytest.raises((ValueError, TimeoutError, asyncio.CancelledError)):
            await invoke(plan, context)

    asyncio.run(run())

    (span,) = exported(exporter)
    assert span.attributes is not None
    assert span.attributes["agnara.invocation.outcome"] == outcome


def test_a_nested_invocation_becomes_a_child_span(traced: Any) -> None:
    hook, exporter = traced
    registry = DIRegistry()

    inner = plan_for([hook], lambda: "inner", registry, capability=INNER)
    inner_context = ExecutionContext(
        Invocation(capability_id=INNER, payload={}, metadata={}),
        DIContainer(registry),
    )

    async def outer_handler() -> str:
        return str(await invoke(inner, inner_context))

    outer = plan_for([hook], outer_handler, registry)
    asyncio.run(invoke(outer, context_for(outer, registry)))

    inner_span, outer_span = exported(exporter)
    assert inner_span.name == str(INNER)
    assert outer_span.name == str(CAPABILITY)
    assert outer_span.parent is None
    assert inner_span.parent is not None
    assert inner_span.parent.span_id == outer_span.context.span_id
    assert inner_span.context.trace_id == outer_span.context.trace_id


def test_concurrent_invocations_do_not_become_each_other_parents(traced: Any) -> None:
    """Sibling tasks copy the context; neither may adopt the other's span."""
    hook, exporter = traced
    registry = DIRegistry()

    async def handler() -> str:
        await asyncio.sleep(0)
        return "ok"

    async def run() -> None:
        plan = plan_for([hook], handler, registry)
        await asyncio.gather(
            *(asyncio.create_task(invoke(plan, context_for(plan, registry))) for _ in range(25))
        )

    asyncio.run(run())

    spans = exported(exporter)
    assert len(spans) == 25
    assert all(span.parent is None for span in spans)
    assert len({span.context.span_id for span in spans}) == 25
    assert len({span.context.trace_id for span in spans}) == 25


def test_the_current_span_is_restored_after_every_invocation(traced: Any) -> None:
    """An unbalanced detach would leak a finished span into unrelated work."""
    hook, exporter = traced
    registry = DIRegistry()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    try:
        plan = plan_for([hook], lambda: "ok", registry)
        with tracer.start_as_current_span("caller") as caller:
            asyncio.run(invoke(plan, context_for(plan, registry)))
            assert caller.is_recording()
    finally:
        provider.shutdown()

    capability_span, caller_span = exported(exporter)
    assert caller_span.name == "caller"
    assert capability_span.parent is not None
    assert capability_span.parent.span_id == caller_span.context.span_id


# ---------------------------------------------------------------------------
# State ownership
# ---------------------------------------------------------------------------


def test_correlation_state_is_released_by_every_terminal_event(traced: Any) -> None:
    """A per-invocation map that only grows is a leak, not a correlation."""
    hook, exporter = traced
    registry = DIRegistry()

    async def run() -> None:
        plan = plan_for([hook], lambda: "ok", registry)
        for _ in range(100):
            await invoke(plan, context_for(plan, registry))

    asyncio.run(run())

    assert len(exported(exporter)) == 100
    assert hook._spans == {}


def test_a_duplicate_registration_strands_no_state(traced: Any) -> None:
    """Registering one hook twice on a plan is a mistake; it must not leak."""
    hook, exporter = traced
    registry = DIRegistry()

    plan = plan_for([hook, hook], lambda: "ok", registry)
    asyncio.run(invoke(plan, context_for(plan, registry)))

    assert hook._spans == {}
    assert len(exported(exporter)) == 2


def test_metrics_and_tracing_hooks_compose_on_one_plan(traced: Any) -> None:
    """E9.2 behavior must be unchanged by the presence of E9.3."""
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    hook, exporter = traced
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    registry = DIRegistry()

    try:
        metrics_hook = OpenTelemetryMetricsHook(meter_provider.get_meter("agnara_telemetry"))
        plan = plan_for([metrics_hook, hook], lambda: "ok", registry)
        asyncio.run(invoke(plan, context_for(plan, registry)))

        data = reader.get_metrics_data()
        assert data is not None
        recorded = {
            metric.name
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
        }
        assert recorded == {"agnara.invocation.count", "agnara.invocation.duration"}
    finally:
        meter_provider.shutdown()

    assert len(exported(exporter)) == 1


def test_the_application_owns_exporter_shutdown() -> None:
    """The hook must not keep a provider alive or shut one down itself."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    hook = OpenTelemetryTracingHook(provider.get_tracer("agnara_telemetry"))

    identity = uuid4().hex
    hook.on_invocation_start(start(identity))
    hook.on_invocation_terminal(terminal(identity, "success"))
    assert len(exported(exporter)) == 1

    provider.shutdown()

    later = uuid4().hex
    hook.on_invocation_start(start(later))
    hook.on_invocation_terminal(terminal(later, "success"))
    assert len(exported(exporter)) == 1
