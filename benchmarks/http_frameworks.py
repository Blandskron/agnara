"""Compare warm in-process ASGI request paths without an HTTP server.

This is reproducible evidence, not a portable ranking. It deliberately keeps
the server, socket, protocol parser and network out of the measurement so a
framework result is never presented as a server result.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import importlib.metadata
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
from typing import Any

from fastapi import FastAPI
from litestar import Litestar, get
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.core.di.resolver import DIContainer
from agnara.execution import ExecutionPlan
from agnara_http._asgi import _ASGIBoundary
from agnara_http._dispatch import _compile_exposures, _HTTPDispatcher, _HTTPExposure

type ASGIApp = Callable[..., Awaitable[None]]

SCHEMA_VERSION = 1
BENCHMARK_NAME = "agnara.http.frameworks"
ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DOCUMENT = {"value": 42}
PATH = "/benchmark"


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """Explicit sampling controls for one benchmark run."""

    iterations: int
    samples: int
    warmups: int


@dataclass(frozen=True, slots=True)
class Scenario:
    """One prebuilt ASGI callable and the semantics represented by its path."""

    name: str
    app: ASGIApp
    semantics: str


async def _direct_asgi(
    scope: dict[str, Any],
    receive: Callable[[], Awaitable[dict[str, Any]]],
    send: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    del receive
    if scope.get("method") != "GET" or scope.get("path") != PATH:
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b""})
        return
    body = json.dumps(EXPECTED_DOCUMENT, separators=(",", ":")).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _starlette_app() -> ASGIApp:
    async def endpoint(request: Request) -> JSONResponse:
        del request
        return JSONResponse(EXPECTED_DOCUMENT)

    return Starlette(routes=[Route(PATH, endpoint=endpoint)])


def _fastapi_app() -> ASGIApp:
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @app.get(PATH)
    async def endpoint() -> dict[str, int]:
        return EXPECTED_DOCUMENT

    return app


def _litestar_app() -> ASGIApp:
    @get(PATH)
    async def endpoint() -> dict[str, int]:
        return EXPECTED_DOCUMENT

    return Litestar(route_handlers=[endpoint], openapi_config=None)


def _agnara_app() -> tuple[ASGIApp, DIContainer]:
    async def endpoint() -> dict[str, int]:
        return EXPECTED_DOCUMENT

    registry = DIRegistry()
    plan = ExecutionPlan.compile(
        CapabilityDefinition(CapabilityId("benchmark", "http"), endpoint),
        registry,
    )
    container = DIContainer(registry)
    dispatcher = _HTTPDispatcher(
        _compile_exposures([_HTTPExposure("GET", PATH, plan)]),
        container,
    )
    return _ASGIBoundary(dispatcher), container


def _scope() -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.5"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": PATH,
        "raw_path": PATH.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("benchmark.local", 80),
        "client": ("127.0.0.1", 1),
    }


async def _exchange(app: ASGIApp) -> list[dict[str, Any]]:
    sent_request = False
    events: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    await app(_scope(), receive, send)
    return events


def _validate(events: list[dict[str, Any]], scenario: str) -> None:
    starts = [event for event in events if event.get("type") == "http.response.start"]
    bodies = [event for event in events if event.get("type") == "http.response.body"]
    if len(starts) != 1 or starts[0].get("status") != 200 or not bodies:
        raise RuntimeError(f"{scenario} returned invalid ASGI events: {events!r}")
    body = b"".join(event.get("body", b"") for event in bodies)
    try:
        document = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{scenario} returned invalid JSON") from exc
    if document != EXPECTED_DOCUMENT:
        raise RuntimeError(f"{scenario} returned {document!r}; expected {EXPECTED_DOCUMENT!r}")


async def _run_batch(scenario: Scenario, iterations: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for _ in range(iterations):
        result = await _exchange(scenario.app)
    return result


def _rotated(scenarios: tuple[Scenario, ...], index: int) -> tuple[Scenario, ...]:
    offset = index % len(scenarios)
    return scenarios[offset:] + scenarios[:offset]


async def _measure(
    scenarios: tuple[Scenario, ...], config: BenchmarkConfig
) -> tuple[dict[str, dict[str, object]], list[list[str]]]:
    for warmup in range(config.warmups):
        for scenario in _rotated(scenarios, warmup):
            _validate(await _run_batch(scenario, config.iterations), scenario.name)

    elapsed: dict[str, list[int]] = {scenario.name: [] for scenario in scenarios}
    sample_order: list[list[str]] = []
    gc_was_enabled = gc.isenabled()
    try:
        gc.disable()
        for sample in range(config.samples):
            ordered = _rotated(scenarios, sample)
            sample_order.append([scenario.name for scenario in ordered])
            for scenario in ordered:
                started_ns = time.perf_counter_ns()
                result = await _run_batch(scenario, config.iterations)
                elapsed_ns = time.perf_counter_ns() - started_ns
                _validate(result, scenario.name)
                elapsed[scenario.name].append(elapsed_ns)
    finally:
        if gc_was_enabled:
            gc.enable()

    results: dict[str, dict[str, object]] = {}
    for scenario in scenarios:
        elapsed_ns = elapsed[scenario.name]
        ns_per_request = [value / config.iterations for value in elapsed_ns]
        results[scenario.name] = {
            "semantics": scenario.semantics,
            "elapsed_ns": elapsed_ns,
            "ns_per_request": ns_per_request,
            "summary_ns_per_request": {
                "minimum": min(ns_per_request),
                "median": statistics.median(ns_per_request),
                "mean": statistics.fmean(ns_per_request),
                "maximum": max(ns_per_request),
                "stdev": statistics.stdev(ns_per_request) if len(ns_per_request) > 1 else 0.0,
            },
        }
    return results, sample_order


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
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def _environment() -> dict[str, object]:
    gil_probe = getattr(sys, "_is_gil_enabled", None)
    clock = time.get_clock_info("perf_counter")
    return {
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_build": list(platform.python_build()),
        "python_executable": sys.executable,
        "gil_enabled": gil_probe() if callable(gil_probe) else None,
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
    """Build each framework once, then measure identical warm ASGI exchanges."""
    agnara, container = _agnara_app()
    scenarios = (
        Scenario("direct_asgi", _direct_asgi, "manual route and JSON serialization"),
        Scenario("starlette", _starlette_app(), "route and JSON response"),
        Scenario("fastapi", _fastapi_app(), "typed route and JSON response"),
        Scenario("litestar", _litestar_app(), "typed route and JSON response"),
        Scenario("agnara_http", agnara, "compiled route, capability invocation and JSON response"),
    )
    try:
        results, sample_order = await _measure(scenarios, config)
    finally:
        await container.aclose()

    direct_median = _median(results["direct_asgi"])
    ratios = {
        name: _median(result) / direct_median
        for name, result in results.items()
        if name != "direct_asgi"
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark": BENCHMARK_NAME,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "git": _git_metadata(),
        "environment": _environment(),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("agnara-http", "fastapi", "starlette", "litestar")
        },
        "config": {
            "iterations_per_sample": config.iterations,
            "samples": config.samples,
            "warmup_rounds": config.warmups,
            "garbage_collector_disabled_during_samples": True,
            "scenario_order": "deterministic rotation",
        },
        "measurement_boundary": {
            "included": "one complete warm in-process ASGI request and response",
            "excluded": [
                "application construction and startup",
                "ASGI server",
                "socket and HTTP protocol parsing",
                "network",
            ],
        },
        "sample_order": sample_order,
        "results": results,
        "median_ratio_to_direct_asgi": ratios,
    }


def _median(result: dict[str, object]) -> float:
    summary = result.get("summary_ns_per_request")
    if not isinstance(summary, dict):
        raise RuntimeError("invalid benchmark summary")
    median = summary.get("median")
    if not isinstance(median, int | float):
        raise RuntimeError("invalid benchmark median")
    return float(median)


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=_positive_integer, default=2_000)
    parser.add_argument("--samples", type=_positive_integer, default=9)
    parser.add_argument("--warmups", type=_positive_integer, default=2)
    parser.add_argument("--json", action="store_true", help="emit the complete JSON record")
    return parser


def _human_output(record: dict[str, object]) -> str:
    config = record["config"]
    results = record["results"]
    ratios = record["median_ratio_to_direct_asgi"]
    versions = record["versions"]
    if not isinstance(config, dict):
        raise RuntimeError("invalid benchmark config")
    if not isinstance(results, dict):
        raise RuntimeError("invalid benchmark results")
    if not isinstance(ratios, dict):
        raise RuntimeError("invalid benchmark ratios")
    if not isinstance(versions, dict):
        raise RuntimeError("invalid benchmark record")
    lines = [
        f"{BENCHMARK_NAME} (lower is better; in-process ASGI, no server)",
        (
            f"{config['samples']} samples x {config['iterations_per_sample']} requests; "
            f"{config['warmup_rounds']} warmup rounds"
        ),
        "versions: " + ", ".join(f"{name} {version}" for name, version in versions.items()),
    ]
    for name, result in results.items():
        if not isinstance(result, dict):
            raise RuntimeError(f"invalid {name} benchmark result")
        summary = result["summary_ns_per_request"]
        if not isinstance(summary, dict):
            raise RuntimeError(f"invalid {name} benchmark summary")
        suffix = ""
        if name != "direct_asgi":
            suffix = f" ({float(ratios[name]):.2f}x direct ASGI)"
        lines.append(f"{name}: {float(summary['median']):,.1f} ns/request{suffix}")
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
    print(json.dumps(record, indent=2, sort_keys=True) if args.json else _human_output(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
