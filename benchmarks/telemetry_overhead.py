"""Measure what the telemetry port costs an application that observes nothing.

E9.1 through E9.5 all declined to make a performance claim. This is where the
no-op cost becomes evidence: how much of an invocation is spent building
lifecycle events, how much of that survives when no hook is registered, and
what each real OpenTelemetry adapter adds on top.

Unlike ``runtime_invocation.py`` this benchmark imports the pinned development
OpenTelemetry SDK, because measuring the adapters is half the point. Exporters
are in-memory: this measures hook work, never network or serialization cost.

It is evidence, not a CI performance threshold. One workstation's latency is
not a portable correctness assertion.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

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

SCHEMA_VERSION = 1
BENCHMARK_NAME = "agnara.telemetry.overhead"
EXPECTED_VALUE = 42
BASELINE_SCENARIO = "no_hooks"
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """Explicit sampling controls for one benchmark run."""

    iterations: int
    samples: int
    warmups: int


@dataclass(frozen=True, slots=True)
class Scenario:
    """One hook configuration and the batch that exercises it."""

    name: str
    run_batch: Callable[[int], Awaitable[object]]
    expected: object


class NoOpHook:
    """A hook that is registered, validated and delivered to, and does nothing.

    This separates the cost of *having* an observer from the cost of what an
    observer does, which is what makes the adapter numbers below readable.
    """

    __slots__ = ()

    def on_invocation_start(self, event: InvocationStartEvent) -> None: ...

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None: ...


async def _handler(value: int) -> int:
    return value + 1


def _fixture(hooks: Sequence[object]) -> tuple[ExecutionPlan, ExecutionContext]:
    registry = DIRegistry()
    definition = CapabilityDefinition(
        id=CapabilityId("benchmark", "increment"),
        handler=_handler,
    )
    plan = ExecutionPlan.compile(definition, registry, hooks=list(hooks))
    context = ExecutionContext(
        Invocation(
            capability_id=definition.id,
            payload={"value": 41},
            metadata={},
        ),
        DIContainer(registry),
    )
    return plan, context


async def _invoke_batch(
    plan: ExecutionPlan,
    context: ExecutionContext,
    iterations: int,
) -> object:
    result: object = None
    for _ in range(iterations):
        result = await invoke(plan, context)
    return result


async def _measure_scenario(scenario: Scenario, config: BenchmarkConfig) -> dict[str, object]:
    for _ in range(config.warmups):
        result = await scenario.run_batch(config.iterations)
        if result != scenario.expected:
            raise RuntimeError(
                f"{scenario.name} returned {result!r}; expected {scenario.expected!r}"
            )

    elapsed_samples: list[int] = []
    gc_was_enabled = gc.isenabled()
    try:
        gc.disable()
        for _ in range(config.samples):
            started_ns = time.perf_counter_ns()
            result = await scenario.run_batch(config.iterations)
            elapsed_ns = time.perf_counter_ns() - started_ns
            if result != scenario.expected:
                raise RuntimeError(
                    f"{scenario.name} returned {result!r}; expected {scenario.expected!r}"
                )
            elapsed_samples.append(elapsed_ns)
    finally:
        if gc_was_enabled:
            gc.enable()

    ns_per_operation = [elapsed / config.iterations for elapsed in elapsed_samples]
    return {
        "elapsed_ns": elapsed_samples,
        "ns_per_operation": ns_per_operation,
        "summary_ns_per_operation": {
            "minimum": min(ns_per_operation),
            "median": statistics.median(ns_per_operation),
            "mean": statistics.fmean(ns_per_operation),
            "maximum": max(ns_per_operation),
            "stdev": statistics.stdev(ns_per_operation) if len(ns_per_operation) > 1 else 0.0,
        },
    }


def _git_metadata() -> dict[str, object]:
    def git(*arguments: str) -> str | None:
        try:
            completed = subprocess.run(
                ["git", *arguments],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        except OSError, subprocess.CalledProcessError:
            return None
        return completed.stdout.strip()

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    return {
        "commit": commit,
        "dirty": None if status is None else bool(status),
    }


def _environment() -> dict[str, object]:
    gil_probe = getattr(sys, "_is_gil_enabled", None)
    gil_enabled = gil_probe() if callable(gil_probe) else None
    clock = time.get_clock_info("perf_counter")
    return {
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_build": list(platform.python_build()),
        "python_executable": sys.executable,
        "gil_enabled": gil_enabled,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER") or "unknown",
        "cpu_count": os.cpu_count(),
        "timer": {
            "implementation": clock.implementation,
            "resolution_seconds": clock.resolution,
            "monotonic": clock.monotonic,
            "adjustable": clock.adjustable,
        },
    }


async def run_benchmark(config: BenchmarkConfig) -> dict[str, object]:
    """Run every hook configuration and return a JSON-ready evidence record."""
    tracer_provider = TracerProvider(shutdown_on_exit=False)
    tracer_provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)

    metrics_hook = OpenTelemetryMetricsHook(meter_provider.get_meter("benchmark"))
    tracing_hook = OpenTelemetryTracingHook(tracer_provider.get_tracer("benchmark"))

    configurations: tuple[tuple[str, tuple[object, ...]], ...] = (
        (BASELINE_SCENARIO, ()),
        ("one_noop_hook", (NoOpHook(),)),
        ("four_noop_hooks", tuple(NoOpHook() for _ in range(4))),
        ("otel_metrics_hook", (metrics_hook,)),
        ("otel_tracing_hook", (tracing_hook,)),
        ("otel_metrics_and_tracing", (metrics_hook, tracing_hook)),
    )

    results: dict[str, object] = {}
    contexts: list[ExecutionContext] = []
    try:
        for name, hooks in configurations:
            plan, context = _fixture(hooks)
            contexts.append(context)
            scenario = Scenario(
                name,
                lambda iterations, plan=plan, context=context: _invoke_batch(
                    plan, context, iterations
                ),
                EXPECTED_VALUE,
            )
            results[name] = await _measure_scenario(scenario, config)
    finally:
        for context in contexts:
            await context.di_container.aclose()
        tracer_provider.shutdown()
        meter_provider.shutdown()

    baseline = results[BASELINE_SCENARIO]
    if not isinstance(baseline, dict):
        raise RuntimeError("invalid baseline benchmark result")
    baseline_summary = baseline["summary_ns_per_operation"]
    if not isinstance(baseline_summary, dict):
        raise RuntimeError("invalid baseline benchmark summary")
    baseline_median = float(baseline_summary["median"])

    overhead: dict[str, float] = {}
    for name, result in results.items():
        if name == BASELINE_SCENARIO or not isinstance(result, dict):
            continue
        summary = result["summary_ns_per_operation"]
        if not isinstance(summary, dict):
            raise RuntimeError(f"invalid {name} benchmark summary")
        overhead[name] = float(summary["median"]) - baseline_median

    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark": BENCHMARK_NAME,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "git": _git_metadata(),
        "environment": _environment(),
        "config": {
            "iterations_per_sample": config.iterations,
            "samples": config.samples,
            "warmup_batches": config.warmups,
            "garbage_collector_disabled_during_samples": True,
            "exporters": "in-memory only; no network or serialization cost",
        },
        "results": results,
        "median_ns_over_baseline": overhead,
    }


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=_positive_integer, default=20_000)
    parser.add_argument("--samples", type=_positive_integer, default=9)
    parser.add_argument("--warmups", type=_positive_integer, default=3)
    parser.add_argument("--json", action="store_true", help="emit the complete JSON record")
    return parser


def _human_output(record: dict[str, object]) -> str:
    config = record["config"]
    results = record["results"]
    overhead = record["median_ns_over_baseline"]
    if not isinstance(config, dict) or not isinstance(results, dict):
        raise RuntimeError("invalid benchmark record")
    lines = [
        f"{BENCHMARK_NAME} (lower is better)",
        (
            f"{config['samples']} samples x {config['iterations_per_sample']} iterations; "
            f"{config['warmup_batches']} warmups"
        ),
    ]
    for name, result in results.items():
        if not isinstance(result, dict):
            raise RuntimeError(f"invalid {name} benchmark result")
        summary = result["summary_ns_per_operation"]
        if not isinstance(summary, dict):
            raise RuntimeError(f"invalid {name} benchmark summary")
        suffix = ""
        if name != BASELINE_SCENARIO:
            if not isinstance(overhead, dict):
                raise RuntimeError("invalid benchmark overhead")
            suffix = f" ({float(overhead[name]):+,.1f} ns over {BASELINE_SCENARIO})"
        lines.append(f"{name}: {float(summary['median']):,.1f} ns/op{suffix}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    record = asyncio.run(
        run_benchmark(
            BenchmarkConfig(
                iterations=args.iterations,
                samples=args.samples,
                warmups=args.warmups,
            )
        )
    )
    if args.json:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(_human_output(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
