"""E9.5: what Agnara is allowed to name, checked against the real conventions.

ADR 0054 and ADR 0055 disclaimed any semantic convention claim. ADR 0057 turns
that disclaimer into a rule with two halves, both enforced here against the
installed ``opentelemetry-semantic-conventions`` package rather than against a
list copied out of a specification:

1. Every attribute Agnara emits is either an ``agnara.``-namespaced custom name
   or a **stable** convention name.
2. No incubating convention name is emitted, so adopting one is a decision
   somebody has to make and record, not something that arrives in a patch.
"""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
from collections.abc import Iterator
from contextlib import suppress
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation, invoke
from agnara_telemetry import OpenTelemetryMetricsHook, OpenTelemetryTracingHook

CAPABILITY = CapabilityId.parse("tests.conventional")

#: Attributes Agnara deliberately adopts from the stable convention set.
ADOPTED_STABLE = frozenset({"error.type"})


def _convention_names(package_path: str) -> frozenset[str]:
    """Every attribute name a semconv attribute subpackage declares."""
    package = importlib.import_module(package_path)
    names: set[str] = set()
    for module_info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package_path}.{module_info.name}")
        for symbol in dir(module):
            if not symbol.isupper():
                continue
            value = getattr(module, symbol)
            if isinstance(value, str) and "." in value and not value.startswith("_"):
                names.add(value)
    return frozenset(names)


@pytest.fixture(scope="module")
def stable_names() -> frozenset[str]:
    return _convention_names("opentelemetry.semconv.attributes")


@pytest.fixture(scope="module")
def incubating_names() -> frozenset[str]:
    return _convention_names("opentelemetry.semconv._incubating.attributes")


@pytest.fixture
def emitted() -> Iterator[tuple[frozenset[str], frozenset[str]]]:
    """Drive every outcome and return the span and metric attribute names."""
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider(shutdown_on_exit=False)
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)

    try:
        tracing = OpenTelemetryTracingHook(tracer_provider.get_tracer("agnara_telemetry"))
        metrics = OpenTelemetryMetricsHook(meter_provider.get_meter("agnara_telemetry"))
        registry = DIRegistry()

        async def run() -> None:
            for outcome in ("success", "failure", "timeout", "cancellation"):

                async def handler(outcome: str = outcome) -> str:
                    if outcome == "failure":
                        raise ValueError("boom")
                    if outcome == "timeout":
                        await asyncio.sleep(60)
                    if outcome == "cancellation":
                        raise asyncio.CancelledError
                    return "ok"

                definition = CapabilityDefinition.declare(id=CAPABILITY, handler=handler)
                plan = ExecutionPlan.compile(definition, registry, hooks=[metrics, tracing])
                deadline = None
                if outcome == "timeout":
                    deadline = asyncio.get_running_loop().time() + 0.01
                context = ExecutionContext(
                    Invocation(
                        capability_id=plan.definition.id,
                        payload={},
                        metadata={},
                        deadline=deadline,
                    ),
                    DIContainer(registry),
                    tracking_id="req-1",
                )
                with suppress(ValueError, TimeoutError, asyncio.CancelledError):
                    await invoke(plan, context)

        asyncio.run(run())

        span_attributes = {
            name for span in span_exporter.get_finished_spans() for name in (span.attributes or {})
        }
        data = reader.get_metrics_data()
        assert data is not None
        metric_attributes = {
            name
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            for point in metric.data.data_points
            for name in (point.attributes or {})
        }
        yield frozenset(span_attributes), frozenset(metric_attributes)
    finally:
        tracer_provider.shutdown()
        meter_provider.shutdown()


def test_every_emitted_attribute_is_agnara_namespaced_or_stable(
    emitted: Any,
    stable_names: frozenset[str],
) -> None:
    span_attributes, metric_attributes = emitted
    unexpected = {
        name
        for name in span_attributes | metric_attributes
        if not name.startswith("agnara.") and name not in stable_names
    }

    assert not unexpected, (
        "an attribute must be agnara-namespaced or a stable convention: "
        + ", ".join(sorted(unexpected))
    )


def test_no_incubating_convention_attribute_is_emitted(
    emitted: Any,
    incubating_names: frozenset[str],
    stable_names: frozenset[str],
) -> None:
    """Adopting an unstable name must be a recorded decision, not a drift."""
    span_attributes, metric_attributes = emitted
    unstable_only = incubating_names - stable_names
    adopted = (span_attributes | metric_attributes) & unstable_only

    assert not adopted, "incubating conventions require an ADR: " + ", ".join(sorted(adopted))


def test_the_adopted_stable_attributes_are_exactly_what_the_adr_records(
    emitted: Any,
    stable_names: frozenset[str],
) -> None:
    """Both directions: nothing adopted silently, nothing recorded but absent."""
    span_attributes, metric_attributes = emitted
    observed = {
        name for name in span_attributes | metric_attributes if not name.startswith("agnara.")
    }

    assert observed == ADOPTED_STABLE
    assert stable_names >= ADOPTED_STABLE


def test_the_gen_ai_tool_vocabulary_is_never_emitted(
    emitted: Any,
    incubating_names: frozenset[str],
) -> None:
    """AGENTS.md: a capability is not intrinsically a tool.

    Emitting ``gen_ai.operation.name=execute_tool`` would assert the opposite
    for an HTTP request made by a human, and the call argument and result
    attributes would export payloads ADR 0054 and ADR 0055 forbid.
    """
    span_attributes, metric_attributes = emitted
    gen_ai = {name for name in incubating_names if name.startswith("gen_ai.")}

    assert gen_ai, "the installed semconv package should declare gen_ai attributes"
    assert not (span_attributes | metric_attributes) & gen_ai


def test_the_mcp_vocabulary_is_never_emitted(
    emitted: Any,
    incubating_names: frozenset[str],
) -> None:
    """MCP must never be the semantic source of truth for a capability."""
    span_attributes, metric_attributes = emitted
    mcp = {name for name in incubating_names if name.startswith("mcp.")}

    assert mcp, "the installed semconv package should declare mcp attributes"
    assert not (span_attributes | metric_attributes) & mcp


def test_error_type_is_carried_only_by_an_actual_error(emitted: Any) -> None:
    """A cancelled or successful invocation must not look like a failure."""
    span_exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    registry = DIRegistry()

    try:
        hook = OpenTelemetryTracingHook(provider.get_tracer("agnara_telemetry"))
        definition = CapabilityDefinition.declare(id=CAPABILITY, handler=lambda: "ok")
        plan = ExecutionPlan.compile(definition, registry, hooks=[hook])
        asyncio.run(
            invoke(
                plan,
                ExecutionContext(
                    Invocation(capability_id=plan.definition.id, payload={}, metadata={}),
                    DIContainer(registry),
                ),
            )
        )
    finally:
        provider.shutdown()

    (span,) = span_exporter.get_finished_spans()
    assert span.attributes is not None
    assert "error.type" not in span.attributes


def test_metric_attributes_stay_narrower_than_span_attributes(emitted: Any) -> None:
    """Recorded on purpose: ``error.type`` was not added to the metrics.

    ``agnara.invocation.outcome`` already carries the same information on every
    measurement, so adding a second attribute present only on failures would
    fragment existing time series for no new signal. See ADR 0057.
    """
    span_attributes, metric_attributes = emitted

    assert metric_attributes == {"agnara.capability.id", "agnara.invocation.outcome"}
    assert "error.type" in span_attributes
