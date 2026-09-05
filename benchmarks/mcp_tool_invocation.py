"""Compare warm in-process MCP ``tools/call`` paths without a network transport.

This is reproducible evidence, not a portable ranking. It measures two
boundaries so a framework result is never presented as a transport result:

``handler``
    the registered ``tools/call`` handler alone, driven with a prebuilt
    request context. This is the framework's own dispatch cost.
``client``
    one complete call through the official in-process ``Client``, which adds
    the client session, the direct dispatcher pair, server-side params
    validation, server middleware and result validation to both frameworks
    equally.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
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

from mcp.server import Server, ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp_types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from agnara import Agnara
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import ExecutionPlan
from agnara_mcp import Mcp, build_mcp_server
from mcp import Client

SCHEMA_VERSION = 1
BENCHMARK_NAME = "agnara.mcp.tool_invocation"
ROOT = Path(__file__).resolve().parents[1]
TOOL_NAME = "echo"
ARGUMENTS = {"value": 41}
EXPECTED_STRUCTURED = {"result": 41}


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """Explicit sampling controls for one benchmark run."""

    iterations: int
    samples: int
    warmups: int


@dataclass(frozen=True, slots=True)
class Scenario:
    """One prebuilt server and the semantics represented by its tool call.

    ``expected_text`` differs by design: the pinned revision leaves the text
    block's shape to the server, and forcing one shape would measure a
    rewritten adapter rather than the real one.
    """

    name: str
    server: Server[Any]
    semantics: str
    expected_text: str
    output_schema: bool
    handler_kind: str


def _request_context() -> ServerRequestContext[Any]:
    """The context a runner would build, without a live session behind it.

    Neither measured handler sends a server-to-client request, so the session
    is never touched. A handler that reached for one would fail here rather
    than quietly measure something else.
    """
    return ServerRequestContext(
        session=None,  # type: ignore[arg-type]
        lifespan_context=None,
        protocol_version="2026-07-28",
        method="tools/call",
        params={"name": TOOL_NAME, "arguments": dict(ARGUMENTS)},
        request_id=1,
    )


def _direct_sdk_server() -> Server[Any]:
    """A lowlevel server whose handler does the dispatch and shaping by hand."""

    async def call_tool(
        _ctx: ServerRequestContext[Any],
        params: CallToolRequestParams,
    ) -> CallToolResult:
        if params.name != TOOL_NAME:
            raise ValueError(f"unknown tool {params.name!r}")
        arguments = params.arguments or {}
        value = arguments["value"]
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("value must be an integer")
        return CallToolResult(
            content=[TextContent(type="text", text=str(value))],
            structured_content={"result": value},
            is_error=False,
        )

    async def list_tools(
        _ctx: ServerRequestContext[Any],
        _params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        return ListToolsResult(tools=[_reference_tool()])

    return Server(
        "benchmark",
        version="test",
        on_call_tool=call_tool,
        on_list_tools=list_tools,
    )


def _reference_tool() -> Tool:
    """The same closed input contract the other two servers publish."""
    return Tool(
        name=TOOL_NAME,
        description="Return the supplied integer.",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )


def _mcpserver_server(*, asynchronous: bool) -> Server[Any]:
    """An official MCPServer exposing the same tool as a sync or async function.

    The distinction matters: MCPServer runs a synchronous tool in an anyio
    worker thread, so a sync-only comparison would measure that execution
    policy rather than dispatch cost.
    """
    server = MCPServer(name="benchmark", version="test")

    if asynchronous:

        @server.tool(name=TOOL_NAME, description="Return the supplied integer.")
        async def echo_async(value: int) -> int:
            return value

    else:

        @server.tool(name=TOOL_NAME, description="Return the supplied integer.")
        def echo_sync(value: int) -> int:
            return value

    return server._lowlevel_server


def _agnara_server(*, asynchronous: bool) -> tuple[Server[Any], DIContainer]:
    """An Agnara MCP server exposing the same capability, sync or async.

    Agnara runs a synchronous handler inline and awaits an asynchronous one,
    so both kinds stay on the calling task.
    """
    app = Agnara("benchmark")

    if asynchronous:

        @app.capability(description="Return the supplied integer.")
        async def echo(value: int) -> int:
            return value

    else:

        @app.capability(description="Return the supplied integer.")
        def echo(value: int) -> int:  # type: ignore[misc]
            return value

    exposed = Mcp(app)
    exposed.tool(echo, name=TOOL_NAME)
    registry = DIRegistry()
    container = DIContainer(registry)
    plans = [ExecutionPlan.compile(app.capabilities[key], registry) for key in app.capabilities]
    server = build_mcp_server(
        exposed.compile(),
        plans,
        container,
        name="benchmark",
        version="test",
    )
    return server, container


def _validate(result: object, scenario: Scenario) -> None:
    name = scenario.name
    if not isinstance(result, CallToolResult):
        raise RuntimeError(f"{name} returned {type(result).__name__}; expected CallToolResult")
    if result.is_error:
        raise RuntimeError(f"{name} returned a tool error: {result.content!r}")
    if result.structured_content != EXPECTED_STRUCTURED:
        raise RuntimeError(f"{name} returned {result.structured_content!r}")
    if len(result.content) != 1:
        raise RuntimeError(f"{name} returned {len(result.content)} content blocks")
    block = result.content[0]
    if not isinstance(block, TextContent) or block.text != scenario.expected_text:
        raise RuntimeError(f"{name} returned unexpected content {block!r}")


def _handler(scenario: Scenario) -> Callable[[Any, CallToolRequestParams], Awaitable[Any]]:
    entry = scenario.server.get_request_handler("tools/call")
    if entry is None:
        raise RuntimeError(f"{scenario.name} registers no tools/call handler")
    return entry.handler


def _rotated[T](items: tuple[T, ...], index: int) -> tuple[T, ...]:
    offset = index % len(items)
    return items[offset:] + items[:offset]


def _summarize(elapsed_ns: list[int], iterations: int) -> dict[str, object]:
    ns_per_call = [value / iterations for value in elapsed_ns]
    return {
        "elapsed_ns": elapsed_ns,
        "ns_per_call": ns_per_call,
        "summary_ns_per_call": {
            "minimum": min(ns_per_call),
            "median": statistics.median(ns_per_call),
            "mean": statistics.fmean(ns_per_call),
            "maximum": max(ns_per_call),
            "stdev": statistics.stdev(ns_per_call) if len(ns_per_call) > 1 else 0.0,
        },
    }


async def _measure(
    scenarios: tuple[Scenario, ...],
    config: BenchmarkConfig,
    batch: Callable[[Scenario, int], Awaitable[object]],
) -> tuple[dict[str, dict[str, object]], list[list[str]]]:
    for warmup in range(config.warmups):
        for scenario in _rotated(scenarios, warmup):
            _validate(await batch(scenario, config.iterations), scenario)

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
                result = await batch(scenario, config.iterations)
                elapsed_ns = time.perf_counter_ns() - started_ns
                _validate(result, scenario)
                elapsed[scenario.name].append(elapsed_ns)
    finally:
        if gc_was_enabled:
            gc.enable()

    results: dict[str, dict[str, object]] = {}
    for scenario in scenarios:
        results[scenario.name] = {
            "semantics": scenario.semantics,
            "text_content": scenario.expected_text,
            "declares_output_schema": scenario.output_schema,
            "handler_kind": scenario.handler_kind,
            **_summarize(elapsed[scenario.name], config.iterations),
        }
    return results, sample_order


def _median(result: dict[str, object]) -> float:
    summary = result.get("summary_ns_per_call")
    if not isinstance(summary, dict):
        raise RuntimeError("invalid benchmark summary")
    median = summary.get("median")
    if not isinstance(median, int | float):
        raise RuntimeError("invalid benchmark median")
    return float(median)


def _ratios(results: dict[str, dict[str, object]], reference: str) -> dict[str, float]:
    baseline = _median(results[reference])
    return {
        name: _median(result) / baseline for name, result in results.items() if name != reference
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
    """Build each server once, then measure identical warm tool calls."""
    agnara_sync, sync_container = _agnara_server(asynchronous=False)
    agnara_async, async_container = _agnara_server(asynchronous=True)
    containers = (sync_container, async_container)
    agnara_semantics = (
        "compiled exposure, scope policy, capability invocation and canonical projection"
    )
    scenarios = (
        Scenario(
            "direct_sdk",
            _direct_sdk_server(),
            "manual dispatch and result construction",
            "41",
            False,
            "async",
        ),
        Scenario(
            "mcpserver_sync",
            _mcpserver_server(asynchronous=False),
            "official MCPServer tool, run in an anyio worker thread",
            "41",
            True,
            "sync",
        ),
        Scenario(
            "mcpserver_async",
            _mcpserver_server(asynchronous=True),
            "official MCPServer tool, awaited on the calling task",
            "41",
            True,
            "async",
        ),
        Scenario(
            "agnara_mcp_sync",
            agnara_sync,
            f"{agnara_semantics}, handler run inline",
            '{"result":41}',
            False,
            "sync",
        ),
        Scenario(
            "agnara_mcp_async",
            agnara_async,
            f"{agnara_semantics}, handler awaited",
            '{"result":41}',
            False,
            "async",
        ),
    )
    handlers = {scenario.name: _handler(scenario) for scenario in scenarios}

    async def handler_batch(scenario: Scenario, iterations: int) -> object:
        handler = handlers[scenario.name]
        context = _request_context()
        result: object = None
        for _ in range(iterations):
            result = await handler(
                context, CallToolRequestParams(name=TOOL_NAME, arguments=dict(ARGUMENTS))
            )
        return result

    try:
        handler_results, handler_order = await _measure(scenarios, config, handler_batch)

        async with contextlib.AsyncExitStack() as stack:
            clients = {
                scenario.name: await stack.enter_async_context(Client(scenario.server, mode="auto"))
                for scenario in scenarios
            }

            async def client_batch(scenario: Scenario, iterations: int) -> object:
                client = clients[scenario.name]
                result: object = None
                for _ in range(iterations):
                    result = await client.call_tool(TOOL_NAME, dict(ARGUMENTS))
                return result

            client_results, client_order = await _measure(scenarios, config, client_batch)
    finally:
        for container in containers:
            await container.aclose()

    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark": BENCHMARK_NAME,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "git": _git_metadata(),
        "environment": _environment(),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("agnara-mcp", "agnara", "mcp", "mcp-types")
        },
        "config": {
            "iterations_per_sample": config.iterations,
            "samples": config.samples,
            "warmup_rounds": config.warmups,
            "garbage_collector_disabled_during_samples": True,
            "scenario_order": "deterministic rotation",
            "reference_scenario": "direct_sdk",
        },
        "measurement_boundaries": {
            "handler": {
                "included": "one registered tools/call handler call with prebuilt params",
                "excluded": [
                    "client session and dispatcher",
                    "server params and result validation",
                    "server middleware",
                    "JSON-RPC framing, sockets and network",
                    "server construction and startup",
                ],
            },
            "client": {
                "included": (
                    "one complete in-process client tool call, including dispatch, "
                    "server middleware and result validation"
                ),
                "excluded": [
                    "JSON-RPC framing, sockets and network",
                    "connection establishment",
                    "server construction and startup",
                ],
                "semantic_difference": (
                    "only mcpserver declares an outputSchema, so only its results are "
                    "revalidated against jsonschema by the client on every call"
                ),
            },
        },
        "sample_order": {"handler": handler_order, "client": client_order},
        "results": {"handler": handler_results, "client": client_results},
        "median_ratio_to_direct_sdk": {
            "handler": _ratios(handler_results, "direct_sdk"),
            "client": _ratios(client_results, "direct_sdk"),
        },
    }


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=_positive_integer, default=1_000)
    parser.add_argument("--samples", type=_positive_integer, default=9)
    parser.add_argument("--warmups", type=_positive_integer, default=2)
    parser.add_argument("--json", action="store_true", help="emit the complete JSON record")
    return parser


def _human_output(record: dict[str, object]) -> str:
    config = record["config"]
    results = record["results"]
    ratios = record["median_ratio_to_direct_sdk"]
    versions = record["versions"]
    if not isinstance(config, dict) or not isinstance(results, dict):
        raise RuntimeError("invalid benchmark record")
    if not isinstance(ratios, dict) or not isinstance(versions, dict):
        raise RuntimeError("invalid benchmark record")
    lines = [
        f"{BENCHMARK_NAME} (lower is better; in-process MCP, no network)",
        (
            f"{config['samples']} samples x {config['iterations_per_sample']} calls; "
            f"{config['warmup_rounds']} warmup rounds"
        ),
        "versions: " + ", ".join(f"{name} {version}" for name, version in versions.items()),
    ]
    for boundary in ("handler", "client"):
        boundary_results = results[boundary]
        boundary_ratios = ratios[boundary]
        if not isinstance(boundary_results, dict) or not isinstance(boundary_ratios, dict):
            raise RuntimeError("invalid benchmark record")
        lines.append(f"[{boundary} boundary]")
        for name, result in boundary_results.items():
            if not isinstance(result, dict):
                raise RuntimeError(f"invalid {name} benchmark result")
            summary = result["summary_ns_per_call"]
            if not isinstance(summary, dict):
                raise RuntimeError(f"invalid {name} benchmark summary")
            suffix = ""
            if name != "direct_sdk":
                suffix = f" ({float(boundary_ratios[name]):.2f}x direct SDK)"
            lines.append(f"  {name}: {float(summary['median']):,.1f} ns/call{suffix}")
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
