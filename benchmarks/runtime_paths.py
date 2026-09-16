"""Measure the Agnara runtime paths that `runtime_invocation.py` does not cover.

`runtime_invocation.py` measures the bare compiled hot path. This benchmark
measures what the 1.0.0 performance program actually has to protect: the cost a
capability pays for dependency injection, policy evaluation, execution identity,
idempotency, nested composition and streaming, plus compile/startup scaling.

Every latency result is reported as a ratio to a reference operation measured in
the *same process and the same run*. Absolute nanoseconds are not portable
between a workstation and a shared CI runner, so an absolute threshold would
make a gate fail on a noisy machine rather than on a real regression. A ratio
moves only when Agnara's own cost moves relative to the interpreter underneath
it, which is the thing a budget is supposed to protect.

Startup is measured differently. Compile cost per capability at two sizes yields
a scaling ratio, which catches the regression that actually matters there --
work that stops being linear in the number of capabilities -- without asserting
a wall-clock number. Peak compile memory is reported as bytes per capability,
which is far less noise-prone than time.

Like the other benchmarks in this directory, this is evidence. The enforced
limits live in `docs/performance/budgets.json` and are checked by
`scripts/check_performance_budgets.py`.
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
import tracemalloc
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agnara.capability import (
    CapabilityDefinition,
    CapabilityId,
    CapabilityRegistry,
    Idempotency,
)
from agnara.core.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    IdempotencyInvocation,
    IdempotencyScope,
    InMemoryIdempotencyStore,
    Invocation,
    Success,
    invoke,
    open_stream,
)
from agnara.policy import Policy, PolicyResult, PolicySuccess, Principal

SCHEMA_VERSION = 1
BENCHMARK_NAME = "agnara.runtime.paths"
ROOT = Path(__file__).resolve().parents[1]

#: The bare-interpreter scenario, used for context rather than for budgets.
REFERENCE_SCENARIO = "direct_async_handler"

#: The plain compiled invocation every feature-overhead budget is measured against.
BASELINE_SCENARIO = "compiled_invoke"

#: Capability counts used for the compile/startup scaling measurement.
STARTUP_SIZES = (100, 1_000)

_PRINCIPAL = Principal("benchmark-actor", scopes={"benchmark:invoke"})


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class Dependency:
    """A dependency whose construction cost is deliberately negligible.

    The benchmark measures what the DI boundary costs, not what a user's
    provider costs. A provider that did real work would hide the framework's
    own overhead behind it.
    """

    __slots__ = ()


class _AllowPolicy:
    """A policy that always allows, so the measurement is the evaluation path.

    A denying policy would short-circuit and measure less work, not more.
    """

    __slots__ = ()

    async def evaluate(self, context: ExecutionContext) -> PolicyResult:
        return PolicySuccess()


class JsonCodec:
    """Minimal codec so the idempotency path stores and reloads real bytes."""

    def encode(self, value: object, /) -> bytes:
        return json.dumps(value, sort_keys=True).encode("utf-8")

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


async def _handler(value: int) -> int:
    return value + 1


async def _direct_batch(iterations: int) -> object:
    result: object = None
    for _ in range(iterations):
        result = await _handler(41)
    return result


def _dependency_registry(count: int) -> tuple[DIRegistry, list[type]]:
    registry = DIRegistry()
    types: list[type] = []
    for index in range(count):
        dependency_type = type(f"Dependency{index}", (Dependency,), {"__slots__": ()})

        def make(bound: type = dependency_type) -> object:
            @provider(scope=Scope.INVOCATION)
            async def supply() -> object:
                return bound()

            return supply

        registry.bind(dependency_type, make())
        types.append(dependency_type)
    return registry, types


def _dependency_plan(count: int) -> tuple[ExecutionPlan, DIContainer]:
    """Compile a capability that takes ``count`` injected dependencies."""
    registry, types = _dependency_registry(count)
    parameters = ", ".join(f"d{index}: T{index}" for index in range(count))
    namespace: dict[str, object] = {f"T{index}": types[index] for index in range(count)}
    source = f"async def handler(value: int, {parameters}) -> int:\n    return value + 1\n"
    exec(compile(source, "<benchmark-di>", "exec"), namespace)
    handler = namespace["handler"]
    definition = CapabilityDefinition(
        id=CapabilityId("benchmark", f"di_{count}"),
        handler=handler,  # ty: ignore[invalid-argument-type]
    )
    plan = ExecutionPlan.compile(definition, registry)
    return plan, DIContainer(registry)


def _policy_plan(count: int) -> tuple[ExecutionPlan, DIContainer]:
    registry = DIRegistry()
    policies: tuple[Policy, ...] = tuple(_AllowPolicy() for _ in range(count))
    definition = CapabilityDefinition(
        id=CapabilityId("benchmark", f"policy_{count}"),
        handler=_handler,
        policies=policies,
    )
    return ExecutionPlan.compile(definition, registry), DIContainer(registry)


def _context(
    plan: ExecutionPlan,
    container: DIContainer,
    *,
    payload: dict[str, object] | None = None,
    principal: Principal | None = None,
    tracking_id: str | None = None,
    idempotency: IdempotencyInvocation | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        Invocation(plan.definition.id, payload if payload is not None else {"value": 41}, {}),
        container,
        principal=principal,
        tracking_id=tracking_id,
        idempotency=idempotency,
    )


async def _invoke_batch(plan: ExecutionPlan, container: DIContainer, iterations: int) -> object:
    result: object = None
    for _ in range(iterations):
        result = await invoke(plan, _context(plan, container))
    return result


async def _identity_batch(plan: ExecutionPlan, container: DIContainer, iterations: int) -> object:
    """Invoke while carrying principal and correlation identity.

    Compared against `compiled_invoke`, the difference is what identity costs.
    """
    result: object = None
    for index in range(iterations):
        result = await invoke(
            plan,
            _context(
                plan,
                container,
                principal=_PRINCIPAL,
                tracking_id=f"tracking-{index}",
            ),
        )
    return result


# ---------------------------------------------------------------------------
# Nested composition
# ---------------------------------------------------------------------------

_CHILD = CapabilityId("benchmark", "child")


def _nested_runtime(depth: int) -> tuple[CapabilityRuntime, DIContainer, CapabilityId]:
    """Build a chain of ``depth`` capabilities, each invoking the next."""
    registry = DIRegistry()

    async def leaf(value: int) -> int:
        return value + 1

    definitions = [CapabilityDefinition(id=_CHILD, handler=leaf)]
    previous = _CHILD
    for level in range(depth):
        current = CapabilityId("benchmark", f"nested_{level}")

        def make(target: CapabilityId = previous) -> Callable[..., Awaitable[int]]:
            async def outer(value: int, invoker: CapabilityInvoker) -> int:
                result = await invoker.invoke(target, {"value": value})
                assert isinstance(result, Success)
                return int(result.value)

            return outer

        definitions.append(CapabilityDefinition(id=current, handler=make()))
        previous = current

    plans = [ExecutionPlan.compile(definition, registry) for definition in definitions]
    capabilities = CapabilityRegistry(plan.definition for plan in plans).freeze()
    container = DIContainer(registry)
    return CapabilityRuntime(capabilities, plans, container), container, previous


async def _nested_batch(
    runtime: CapabilityRuntime,
    container: DIContainer,
    entry: CapabilityId,
    iterations: int,
) -> object:
    result: object = None
    for _ in range(iterations):
        result = await runtime.invoke_result(
            ExecutionContext(
                Invocation(entry, {"value": 41}, {}),
                container,
                principal=_PRINCIPAL,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def _idempotent_plan() -> tuple[ExecutionPlan, DIContainer]:
    registry = DIRegistry()
    definition = CapabilityDefinition(
        id=CapabilityId("benchmark", "idempotent"),
        handler=_handler,
        idempotency=Idempotency.YES,
    )
    return ExecutionPlan.compile(definition, registry), DIContainer(registry)


def _idempotency(
    plan: ExecutionPlan, store: InMemoryIdempotencyStore, key: str
) -> IdempotencyInvocation:
    return IdempotencyInvocation(
        IdempotencyScope(plan.definition.id, _PRINCIPAL.identity, key, b"benchmark-fingerprint"),
        store,
        JsonCodec(),
        30,
        60,
    )


async def _idempotency_miss_batch(
    plan: ExecutionPlan, container: DIContainer, iterations: int
) -> object:
    """Every iteration claims a fresh key, so this is the store-write path."""
    store = InMemoryIdempotencyStore(max_entries=iterations + 8)
    result: object = None
    for index in range(iterations):
        result = await invoke(
            plan,
            _context(
                plan,
                container,
                principal=_PRINCIPAL,
                idempotency=_idempotency(plan, store, f"miss-{index}"),
            ),
        )
    return result


async def _idempotency_hit_batch(
    plan: ExecutionPlan, container: DIContainer, iterations: int
) -> object:
    """Every iteration replays one stored result, so this is the reuse path."""
    store = InMemoryIdempotencyStore()
    result: object = None
    for _ in range(iterations):
        result = await invoke(
            plan,
            _context(
                plan,
                container,
                principal=_PRINCIPAL,
                idempotency=_idempotency(plan, store, "hit"),
            ),
        )
    return result


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

_STREAM_UNITS = 16


def _stream_plan() -> tuple[ExecutionPlan, DIContainer]:
    registry = DIRegistry()

    async def emit() -> AsyncIterator[int]:
        for index in range(_STREAM_UNITS):
            yield index

    definition = CapabilityDefinition(
        id=CapabilityId("benchmark", "stream"),
        handler=emit,
        streaming=True,
    )
    return ExecutionPlan.compile(definition, registry), DIContainer(registry)


async def _stream_batch(plan: ExecutionPlan, container: DIContainer, iterations: int) -> object:
    """Measured per emitted unit, not per stream, so the ratio is comparable."""
    total = 0
    for _ in range(iterations):
        async with open_stream(plan, _context(plan, container, payload={})) as stream:
            async for _unit in stream:
                total += 1
    return total


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


async def _measure_scenario(
    scenario: Scenario, config: BenchmarkConfig, *, operations_per_iteration: int = 1
) -> dict[str, object]:
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

    divisor = config.iterations * operations_per_iteration
    ns_per_operation = [elapsed / divisor for elapsed in elapsed_samples]
    return {
        "elapsed_ns": elapsed_samples,
        "ns_per_operation": ns_per_operation,
        "operations_per_iteration": operations_per_iteration,
        "summary_ns_per_operation": {
            "minimum": min(ns_per_operation),
            "median": statistics.median(ns_per_operation),
            "mean": statistics.fmean(ns_per_operation),
            "maximum": max(ns_per_operation),
            "stdev": statistics.stdev(ns_per_operation) if len(ns_per_operation) > 1 else 0.0,
        },
    }


def _measure_startup(size: int, samples: int) -> dict[str, object]:
    """Compile ``size`` capabilities, reporting time and peak memory per capability."""
    registry = DIRegistry()
    definitions = [
        CapabilityDefinition(id=CapabilityId("benchmark", f"startup_{index}"), handler=_handler)
        for index in range(size)
    ]

    elapsed_samples: list[int] = []
    gc_was_enabled = gc.isenabled()
    try:
        gc.disable()
        for _ in range(samples):
            started_ns = time.perf_counter_ns()
            plans = [ExecutionPlan.compile(definition, registry) for definition in definitions]
            elapsed_samples.append(time.perf_counter_ns() - started_ns)
            if len(plans) != size:
                raise RuntimeError("compile produced the wrong plan count")
            del plans
    finally:
        if gc_was_enabled:
            gc.enable()

    tracemalloc.start()
    try:
        retained = [ExecutionPlan.compile(definition, registry) for definition in definitions]
        _current, peak = tracemalloc.get_traced_memory()
        if len(retained) != size:
            raise RuntimeError("compile produced the wrong plan count")
    finally:
        tracemalloc.stop()

    ns_per_capability = [elapsed / size for elapsed in elapsed_samples]
    return {
        "capabilities": size,
        "elapsed_ns": elapsed_samples,
        "ns_per_capability": ns_per_capability,
        "median_ns_per_capability": statistics.median(ns_per_capability),
        "peak_bytes_per_capability": peak / size,
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


async def _scenarios() -> tuple[list[tuple[Scenario, int]], list[Callable[[], Awaitable[None]]]]:
    """Build every scenario plus the teardown callbacks its fixtures require."""
    plain_plan, plain_container = _dependency_plan(0)
    di_one_plan, di_one_container = _dependency_plan(1)
    di_ten_plan, di_ten_container = _dependency_plan(10)
    policy_one_plan, policy_one_container = _policy_plan(1)
    policy_three_plan, policy_three_container = _policy_plan(3)
    idempotent_plan, idempotent_container = _idempotent_plan()
    stream_plan, stream_container = _stream_plan()
    nested_one, nested_one_container, nested_one_entry = _nested_runtime(1)
    nested_three, nested_three_container, nested_three_entry = _nested_runtime(3)

    expected = 42
    scenarios: list[tuple[Scenario, int]] = [
        (Scenario(REFERENCE_SCENARIO, _direct_batch, expected), 1),
        (
            Scenario(
                "compiled_invoke",
                lambda n: _invoke_batch(plain_plan, plain_container, n),
                expected,
            ),
            1,
        ),
        (
            Scenario(
                "dependency_injection_one",
                lambda n: _invoke_batch(di_one_plan, di_one_container, n),
                expected,
            ),
            1,
        ),
        (
            Scenario(
                "dependency_injection_ten",
                lambda n: _invoke_batch(di_ten_plan, di_ten_container, n),
                expected,
            ),
            1,
        ),
        (
            Scenario(
                "policy_evaluation_one",
                lambda n: _invoke_batch(policy_one_plan, policy_one_container, n),
                expected,
            ),
            1,
        ),
        (
            Scenario(
                "policy_evaluation_three",
                lambda n: _invoke_batch(policy_three_plan, policy_three_container, n),
                expected,
            ),
            1,
        ),
        (
            Scenario(
                "execution_identity",
                lambda n: _identity_batch(plain_plan, plain_container, n),
                expected,
            ),
            1,
        ),
        (
            Scenario(
                "idempotency_miss",
                lambda n: _idempotency_miss_batch(idempotent_plan, idempotent_container, n),
                expected,
            ),
            1,
        ),
        (
            Scenario(
                "idempotency_hit",
                lambda n: _idempotency_hit_batch(idempotent_plan, idempotent_container, n),
                expected,
            ),
            1,
        ),
        (
            Scenario(
                "nested_depth_one",
                lambda n: _nested_batch(nested_one, nested_one_container, nested_one_entry, n),
                Success(expected),
            ),
            1,
        ),
        (
            Scenario(
                "nested_depth_three",
                lambda n: _nested_batch(
                    nested_three, nested_three_container, nested_three_entry, n
                ),
                Success(expected),
            ),
            1,
        ),
    ]

    async def stream_batch(n: int) -> object:
        return await _stream_batch(stream_plan, stream_container, n)

    def stream_expected(n: int) -> int:
        return n * _STREAM_UNITS

    scenarios.append(
        (
            Scenario("streaming_unit", stream_batch, None),
            _STREAM_UNITS,
        )
    )

    containers = (
        plain_container,
        di_one_container,
        di_ten_container,
        policy_one_container,
        policy_three_container,
        idempotent_container,
        stream_container,
    )
    runtimes = (nested_one, nested_three)

    async def teardown() -> None:
        for runtime in runtimes:
            await runtime.aclose()
        for container in containers:
            await container.aclose()

    return scenarios, [teardown]


async def run_benchmark(config: BenchmarkConfig) -> dict[str, object]:
    """Run every scenario and return JSON-ready evidence."""
    scenarios, teardowns = await _scenarios()

    results: dict[str, object] = {}
    try:
        for scenario, operations in scenarios:
            if scenario.name == "streaming_unit":
                # The stream scenario's expected value depends on the batch size,
                # so it is validated by the batch itself rather than by equality.
                scenario = Scenario(
                    scenario.name,
                    scenario.run_batch,
                    config.iterations * _STREAM_UNITS,
                )
            results[scenario.name] = await _measure_scenario(
                scenario, config, operations_per_iteration=operations
            )
    finally:
        for teardown in teardowns:
            await teardown()

    reference = results[REFERENCE_SCENARIO]
    if not isinstance(reference, dict):
        raise RuntimeError("invalid reference benchmark result")
    reference_summary = reference["summary_ns_per_operation"]
    if not isinstance(reference_summary, dict):
        raise RuntimeError("invalid reference benchmark summary")
    reference_median = float(reference_summary["median"])

    def _median(name: str) -> float:
        entry = results[name]
        if not isinstance(entry, dict):
            raise RuntimeError(f"invalid {name} benchmark result")
        summary = entry["summary_ns_per_operation"]
        if not isinstance(summary, dict):
            raise RuntimeError(f"invalid {name} benchmark summary")
        return float(summary["median"])

    ratios: dict[str, float] = {}
    for name in results:
        if name == REFERENCE_SCENARIO:
            continue
        ratios[name] = _median(name) / reference_median

    # A bare `await handler()` costs ~100ns, close enough to loop and timer
    # overhead that it moves by 2x between runs on a busy machine. Dividing a
    # ~10us runtime path by it inherits that noise. Feature overhead is
    # therefore budgeted against `compiled_invoke`, which is the same order of
    # magnitude and moves with the same machine conditions; the ratio to the
    # bare handler is kept only as context for how much the framework costs.
    invoke_median = _median(BASELINE_SCENARIO)
    baseline_ratios = {
        name: _median(name) / invoke_median
        for name in results
        if name not in (REFERENCE_SCENARIO, BASELINE_SCENARIO)
    }

    startup = {str(size): _measure_startup(size, config.samples) for size in STARTUP_SIZES}
    smallest, largest = (str(size) for size in STARTUP_SIZES)
    scaling = float(startup[largest]["median_ns_per_capability"]) / float(
        startup[smallest]["median_ns_per_capability"]
    )

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
            "reference_scenario": REFERENCE_SCENARIO,
            "stream_units_per_iteration": _STREAM_UNITS,
        },
        "results": results,
        "median_ratio_to_reference": ratios,
        "median_ratio_to_compiled_invoke": baseline_ratios,
        "startup": startup,
        "startup_scaling_ratio": scaling,
    }


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=_positive_integer, default=2_000)
    parser.add_argument("--samples", type=_positive_integer, default=7)
    parser.add_argument("--warmups", type=_positive_integer, default=2)
    parser.add_argument("--json", action="store_true", help="emit the complete JSON record")
    return parser


def _human_output(record: dict[str, object]) -> str:
    config = record["config"]
    results = record["results"]
    ratios = record["median_ratio_to_reference"]
    if (
        not isinstance(config, dict)
        or not isinstance(results, dict)
        or not isinstance(ratios, dict)
    ):
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
        suffix = "" if name == REFERENCE_SCENARIO else f" ({float(ratios[name]):.2f}x reference)"
        lines.append(f"{name}: {float(summary['median']):,.1f} ns/op{suffix}")
    startup = record["startup"]
    if not isinstance(startup, dict):
        raise RuntimeError("invalid startup record")
    for size, entry in startup.items():
        if not isinstance(entry, dict):
            raise RuntimeError("invalid startup entry")
        lines.append(
            f"startup[{size}]: {float(entry['median_ns_per_capability']):,.1f} ns/capability, "
            f"{float(entry['peak_bytes_per_capability']):,.0f} bytes/capability"
        )
    lines.append(f"startup scaling ratio: {float(record['startup_scaling_ratio']):.2f}x")
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
