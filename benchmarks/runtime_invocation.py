"""Measure the warm, compiled Agnara invocation hot path.

This benchmark intentionally uses only the standard library. It is evidence,
not a CI performance threshold: machine load and Python builds vary too much
for one workstation's latency to be a portable correctness assertion.
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

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
    invoke,
    invoke_result,
)

SCHEMA_VERSION = 1
BENCHMARK_NAME = "agnara.runtime.invocation"
EXPECTED_VALUE = 42
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """Explicit sampling controls for one benchmark run."""

    iterations: int
    samples: int
    warmups: int


@dataclass(frozen=True, slots=True)
class Scenario:
    """One runtime path and the value it must produce."""

    name: str
    run_batch: Callable[[int], Awaitable[object]]
    expected: object


async def _handler(value: int) -> int:
    return value + 1


async def _direct_batch(iterations: int) -> object:
    result: object = None
    for _ in range(iterations):
        result = await _handler(41)
    return result


def _runtime_fixture() -> tuple[ExecutionPlan, ExecutionContext]:
    registry = DIRegistry()
    definition = CapabilityDefinition(
        id=CapabilityId("benchmark", "increment"),
        handler=_handler,
    )
    plan = ExecutionPlan.compile(definition, registry)
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


async def _invoke_result_batch(
    plan: ExecutionPlan,
    context: ExecutionContext,
    iterations: int,
) -> object:
    result: object = None
    for _ in range(iterations):
        result = await invoke_result(plan, context)
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
    """Run every scenario against one precompiled plan and return JSON-ready evidence."""
    plan, context = _runtime_fixture()
    scenarios = (
        Scenario("direct_async_handler", _direct_batch, EXPECTED_VALUE),
        Scenario(
            "compiled_invoke",
            lambda iterations: _invoke_batch(plan, context, iterations),
            EXPECTED_VALUE,
        ),
        Scenario(
            "canonical_invoke_result",
            lambda iterations: _invoke_result_batch(plan, context, iterations),
            Success(EXPECTED_VALUE),
        ),
    )

    results: dict[str, object] = {}
    try:
        for scenario in scenarios:
            results[scenario.name] = await _measure_scenario(scenario, config)
    finally:
        await context.di_container.aclose()

    direct_summary = results["direct_async_handler"]
    if not isinstance(direct_summary, dict):
        raise RuntimeError("invalid direct benchmark result")
    direct_stats = direct_summary["summary_ns_per_operation"]
    if not isinstance(direct_stats, dict):
        raise RuntimeError("invalid direct benchmark summary")
    direct_median = float(direct_stats["median"])

    ratios: dict[str, float] = {}
    for name in ("compiled_invoke", "canonical_invoke_result"):
        scenario_result = results[name]
        if not isinstance(scenario_result, dict):
            raise RuntimeError(f"invalid {name} benchmark result")
        summary = scenario_result["summary_ns_per_operation"]
        if not isinstance(summary, dict):
            raise RuntimeError(f"invalid {name} benchmark summary")
        ratios[name] = float(summary["median"]) / direct_median

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
        },
        "results": results,
        "median_ratio_to_direct": ratios,
    }


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=_positive_integer, default=10_000)
    parser.add_argument("--samples", type=_positive_integer, default=7)
    parser.add_argument("--warmups", type=_positive_integer, default=2)
    parser.add_argument("--json", action="store_true", help="emit the complete JSON record")
    return parser


def _human_output(record: dict[str, object]) -> str:
    config = record["config"]
    results = record["results"]
    ratios = record["median_ratio_to_direct"]
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
        if name != "direct_async_handler":
            if not isinstance(ratios, dict):
                raise RuntimeError("invalid benchmark ratios")
            suffix = f" ({float(ratios[name]):.2f}x direct)"
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
