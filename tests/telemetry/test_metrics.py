"""E9.2 real SDK evidence for the explicit metrics bridge."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import patch

import pytest
from opentelemetry.metrics import NoOpMeterProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    InvocationStartEvent,
    InvocationTerminalEvent,
    invoke,
    invoke_result,
)
from agnara_telemetry import OpenTelemetryMetricsHook

CAPABILITY = CapabilityId.parse("tests.measured")


@pytest.fixture
def recorded() -> Iterator[tuple[OpenTelemetryMetricsHook, InMemoryMetricReader]]:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    try:
        yield OpenTelemetryMetricsHook(provider.get_meter("agnara_telemetry")), reader
    finally:
        provider.shutdown()


def measurements(reader: InMemoryMetricReader) -> dict[str, Any]:
    data = reader.get_metrics_data()
    assert data is not None
    return {
        metric.name: metric
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }


def terminal(outcome: str, duration: int = 250_000_000) -> InvocationTerminalEvent:
    return InvocationTerminalEvent(CAPABILITY, "secret-tracking-id", duration, outcome)


def plan_for(hook: Any, handler: Any) -> ExecutionPlan:
    definition = CapabilityDefinition.declare(id=CAPABILITY, handler=handler)
    return ExecutionPlan.compile(definition, DIRegistry(), hooks=[hook])


def context_for(plan: ExecutionPlan, deadline: float | None = None) -> ExecutionContext:
    return ExecutionContext(
        Invocation(
            capability_id=plan.definition.id,
            payload={},
            metadata={"tracking_id": "same-secret-id", "secret": "must-not-export"},
            deadline=deadline,
        ),
        DIContainer(DIRegistry()),
    )


@pytest.mark.parametrize(
    "outcome", ["success", "failure", "timeout", "cancellation", "private-error"]
)
def test_exact_units_values_and_attribute_allowlist(recorded: Any, outcome: str) -> None:
    hook, reader = recorded
    hook.on_invocation_start(InvocationStartEvent(CAPABILITY, "secret-tracking-id"))
    assert reader.get_metrics_data() is None
    hook.on_invocation_terminal(terminal(outcome))
    metrics = measurements(reader)
    assert set(metrics) == {"agnara.invocation.count", "agnara.invocation.duration"}
    counter, histogram = metrics["agnara.invocation.count"], metrics["agnara.invocation.duration"]
    assert counter.unit == "1"
    assert histogram.unit == "s"
    assert counter.data.data_points[0].value == 1
    point = histogram.data.data_points[0]
    assert (point.count, point.sum, point.min, point.max) == (1, 0.25, 0.25, 0.25)
    expected = {
        "agnara.capability.id": "tests.measured",
        "agnara.invocation.outcome": "unknown" if outcome == "private-error" else outcome,
    }
    for metric in metrics.values():
        assert dict(metric.data.data_points[0].attributes) == expected


def test_negative_duration_is_rejected_before_any_recording(recorded: Any) -> None:
    hook, reader = recorded
    with pytest.raises(ValueError, match="non-negative"):
        hook.on_invocation_terminal(terminal("success", -1))
    assert reader.get_metrics_data() is None
    hook.on_invocation_terminal(terminal("success", 0))
    assert measurements(reader)["agnara.invocation.duration"].data.data_points[0].sum == 0


def test_noop_api_works_without_installing_a_global_provider() -> None:
    meter = NoOpMeterProvider().get_meter("no-op")
    with (
        patch(
            "opentelemetry.metrics.get_meter_provider", side_effect=AssertionError("global read")
        ),
        patch(
            "opentelemetry.metrics.set_meter_provider", side_effect=AssertionError("global write")
        ),
    ):
        hook = OpenTelemetryMetricsHook(meter)

        def handler() -> str:
            return "ok"

        plan = plan_for(hook, handler)
        assert asyncio.run(invoke(plan, context_for(plan))) == "ok"


def test_invalid_meter_fails_during_composition() -> None:
    invalid: Any = None
    with pytest.raises(TypeError, match="OpenTelemetry Meter"):
        OpenTelemetryMetricsHook(invalid)


@pytest.mark.parametrize("outcome", ["success", "failure", "timeout", "cancellation"])
def test_real_runtime_terminal_outcomes(recorded: Any, outcome: str) -> None:
    hook, reader = recorded

    async def run() -> None:
        entered = asyncio.Event()

        async def handler() -> str:
            if outcome == "failure":
                raise ValueError("private failure details")
            if outcome in {"timeout", "cancellation"}:
                entered.set()
                await asyncio.Event().wait()
            return "private result"

        plan = plan_for(hook, handler)
        deadline = asyncio.get_running_loop().time() + 0.01 if outcome == "timeout" else None
        context = context_for(plan, deadline)
        if outcome == "cancellation":
            async with asyncio.TaskGroup() as group:
                task = group.create_task(invoke(plan, context))
                await entered.wait()
                task.cancel()
            assert task.cancelled()
        elif outcome == "failure":
            with pytest.raises(ValueError, match="private failure"):
                await invoke(plan, context)
        elif outcome == "timeout":
            with pytest.raises(TimeoutError):
                await invoke(plan, context)
        else:
            assert await invoke(plan, context) == "private result"

    asyncio.run(run())
    metrics = measurements(reader)
    point = metrics["agnara.invocation.count"].data.data_points[0]
    assert point.value == 1
    assert dict(point.attributes) == {
        "agnara.capability.id": "tests.measured",
        "agnara.invocation.outcome": outcome,
    }
    assert metrics["agnara.invocation.duration"].data.data_points[0].sum >= 0


def test_nested_and_overlapping_invocations_with_repeated_tracking_ids(recorded: Any) -> None:
    hook, reader = recorded

    async def run() -> None:
        arrived = 0
        ready = asyncio.Event()

        async def child() -> str:
            nonlocal arrived
            arrived += 1
            if arrived == 8:
                ready.set()
            await ready.wait()
            return "ok"

        child_plan = plan_for(hook, child)

        async def parent() -> str:
            return await invoke(child_plan, context_for(child_plan))

        parent_plan = plan_for(hook, parent)
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(invoke(parent_plan, context_for(parent_plan))) for _ in range(8)
            ]
        assert [task.result() for task in tasks] == ["ok"] * 8

    asyncio.run(run())
    metrics = measurements(reader)
    assert metrics["agnara.invocation.count"].data.data_points[0].value == 16
    assert metrics["agnara.invocation.duration"].data.data_points[0].count == 16


def test_shared_hook_records_from_multiple_threads(recorded: Any) -> None:
    hook, reader = recorded

    def handler() -> str:
        return "ok"

    plan = plan_for(hook, handler)

    def call(_: int) -> str:
        return asyncio.run(invoke(plan, context_for(plan)))

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(call, range(32))) == ["ok"] * 32
    metrics = measurements(reader)
    assert metrics["agnara.invocation.count"].data.data_points[0].value == 32
    assert metrics["agnara.invocation.duration"].data.data_points[0].count == 32


def test_canonical_failure_return_retains_core_success_semantics(recorded: Any) -> None:
    hook, reader = recorded
    failure = Failure(FailureCode.INTERNAL_FAILURE, "private canonical details")

    def handler() -> Failure:
        return failure

    plan = plan_for(hook, handler)
    assert asyncio.run(invoke_result(plan, context_for(plan))) is failure
    point = measurements(reader)["agnara.invocation.count"].data.data_points[0]
    assert dict(point.attributes)["agnara.invocation.outcome"] == "success"


def test_provider_shutdown_and_flush_remain_application_owned() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    try:
        with (
            patch.object(provider, "shutdown", wraps=provider.shutdown) as shutdown,
            patch.object(provider, "force_flush", wraps=provider.force_flush) as flush,
        ):
            hook = OpenTelemetryMetricsHook(provider.get_meter("agnara_telemetry"))
            hook.on_invocation_terminal(terminal("success"))
            shutdown.assert_not_called()
            flush.assert_not_called()
            assert provider.force_flush()
            assert measurements(reader)["agnara.invocation.count"].data.data_points[0].value == 1
    finally:
        provider.shutdown()


def test_instrument_failure_does_not_change_runtime_result() -> None:
    meter = NoOpMeterProvider().get_meter("broken")
    instrument = meter.create_counter("broken.count")
    with (
        patch.object(meter, "create_counter", return_value=instrument),
        patch.object(instrument, "add", side_effect=RuntimeError("exporter unavailable")),
    ):
        hook = OpenTelemetryMetricsHook(meter)

        def handler() -> str:
            return "ok"

        plan = plan_for(hook, handler)
        assert asyncio.run(invoke(plan, context_for(plan))) == "ok"
