"""E9.4 evidence: whether a capability span joins a caller's trace.

ADR 0055 scoped remote parenting out of E9.3, so this suite establishes what
actually happens across the real HTTP dispatcher and the real MCP invoker,
rather than a re-implementation of either. The claim under test is narrow: the
span the E9.3 hook opens inherits whatever OpenTelemetry context is current at
invocation, so propagation is an application responsibility that works, and
never happens by accident.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextvars import Token
from dataclasses import dataclass
from typing import Any, cast

import pytest
from mcp.server import ServerRequestContext
from mcp_types import CallToolRequestParams
from opentelemetry.context import Context, attach, detach
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from agnara import Agnara
from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.core.di.resolver import DIContainer
from agnara.execution import ExecutionPlan
from agnara_http._dispatch import (
    _compile_exposures,
    _HTTPDispatcher,
    _HTTPExposure,
)
from agnara_mcp import Mcp, McpToolInvoker
from agnara_telemetry import OpenTelemetryTracingHook

#: A W3C trace context a caller would send. Taken from the specification's own
#: example so the identifiers are recognisable rather than invented.
REMOTE_TRACE_ID = 0x4BF92F3577B34DA6A3CE929D0E0E4736
REMOTE_SPAN_ID = 0x00F067AA0BA902B7
REMOTE_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

SECOND_TRACE_ID = 0x1234567890ABCDEF1234567890ABCDEF
SECOND_TRACEPARENT = "00-1234567890abcdef1234567890abcdef-00f067aa0ba902b8-01"


@pytest.fixture
def spans() -> Iterator[tuple[OpenTelemetryTracingHook, InMemorySpanExporter]]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        yield OpenTelemetryTracingHook(provider.get_tracer("agnara_telemetry")), exporter
    finally:
        provider.shutdown()


def propagated(traceparent: str | None) -> Token[Context] | None:
    """Do what an application's instrumentation does, and nothing more.

    Agnara never reads this header. Extracting it here is the test standing in
    for the application, which is precisely the boundary under test.
    """
    if traceparent is None:
        return None
    carrier = {"traceparent": traceparent}
    return attach(TraceContextTextMapPropagator().extract(carrier))


def parent_of(span: ReadableSpan) -> int | None:
    return None if span.parent is None else span.parent.span_id


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def http_surface(hook: OpenTelemetryTracingHook) -> _HTTPDispatcher:
    def show() -> dict[str, bool]:
        return {"ok": True}

    plan = ExecutionPlan.compile(
        CapabilityDefinition(CapabilityId("tests", "show"), show),
        DIRegistry(),
        hooks=[hook],
    )
    return _HTTPDispatcher(
        _compile_exposures([_HTTPExposure("GET", "/v1/show", plan)]),
        DIContainer(DIRegistry()),
        None,
    )


async def http_request(
    served: _HTTPDispatcher,
    traceparent: str | None = None,
) -> list[dict[str, Any]]:
    """Drive one real request, optionally inside an extracted remote context."""
    events: list[dict[str, Any]] = []
    pending = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    headers: list[tuple[bytes, bytes]] = []
    if traceparent is not None:
        headers.append((b"traceparent", traceparent.encode("ascii")))

    token = propagated(traceparent)
    try:
        await served(
            {
                "type": "http",
                "method": "GET",
                "path": "/v1/show",
                "raw_path": b"/v1/show",
                "query_string": b"",
                "root_path": "",
                "headers": headers,
            },
            receive,
            send,
        )
    finally:
        if token is not None:
            detach(token)
    return events


def test_an_http_capability_span_joins_a_propagated_caller_trace(spans: Any) -> None:
    hook, exporter = spans
    served = http_surface(hook)

    events = asyncio.run(http_request(served, REMOTE_TRACEPARENT))

    assert events[0]["status"] == 200
    assert json.loads(events[1]["body"]) == {"ok": True}
    (span,) = exporter.get_finished_spans()
    assert span.context.trace_id == REMOTE_TRACE_ID
    assert parent_of(span) == REMOTE_SPAN_ID


def test_an_http_capability_span_is_a_root_without_propagation(spans: Any) -> None:
    """The header alone must do nothing: Agnara does not read it."""
    hook, exporter = spans
    served = http_surface(hook)

    # The header is present on the request and deliberately not extracted.
    events: list[dict[str, Any]] = []
    pending = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    asyncio.run(
        served(
            {
                "type": "http",
                "method": "GET",
                "path": "/v1/show",
                "raw_path": b"/v1/show",
                "query_string": b"",
                "root_path": "",
                "headers": [(b"traceparent", REMOTE_TRACEPARENT.encode("ascii"))],
            },
            receive,
            send,
        )
    )

    (span,) = exporter.get_finished_spans()
    assert span.parent is None
    assert span.context.trace_id != REMOTE_TRACE_ID


@pytest.mark.parametrize(
    "traceparent",
    [
        "",
        "not-a-traceparent",
        "00-00000000000000000000000000000000-0000000000000000-01",
        "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7",
        "00-" + "z" * 32 + "-00f067aa0ba902b7-01",
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01, injected",
    ],
)
def test_a_malformed_traceparent_neither_links_nor_raises(spans: Any, traceparent: str) -> None:
    """A caller controls this header; a bad one must be inert, not fatal.

    ``ff`` is the one version the W3C specification forbids outright, which is
    why it appears here rather than among the forward-compatible versions.
    """
    hook, exporter = spans
    served = http_surface(hook)

    events = asyncio.run(http_request(served, traceparent))

    assert events[0]["status"] == 200
    (span,) = exporter.get_finished_spans()
    assert span.parent is None


@pytest.mark.parametrize("version", ["01", "99", "fe"])
def test_an_unknown_traceparent_version_still_links(spans: Any, version: str) -> None:
    """Not a defect: W3C requires forward compatibility for future versions.

    This was written expecting ``99`` to be rejected. The propagator linked it,
    the specification agrees with the propagator, and the expectation was
    wrong. Pinned so the behaviour is a recorded decision rather than a
    surprise for whoever reads a trace containing one.
    """
    hook, exporter = spans
    served = http_surface(hook)

    asyncio.run(
        http_request(served, f"{version}-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
    )

    (span,) = exporter.get_finished_spans()
    assert span.context.trace_id == REMOTE_TRACE_ID
    assert parent_of(span) == REMOTE_SPAN_ID


def test_concurrent_requests_do_not_contaminate_each_other(spans: Any) -> None:
    """Each request runs in its own task, so each holds its own context copy."""
    hook, exporter = spans
    served = http_surface(hook)

    async def run() -> None:
        await asyncio.gather(
            *(
                asyncio.create_task(http_request(served, traceparent))
                for traceparent in (REMOTE_TRACEPARENT, SECOND_TRACEPARENT, None) * 5
            )
        )

    asyncio.run(run())

    traces = [span.context.trace_id for span in exporter.get_finished_spans()]
    assert len(traces) == 15
    assert traces.count(REMOTE_TRACE_ID) == 5
    assert traces.count(SECOND_TRACE_ID) == 5
    # The five unpropagated requests are each their own root trace.
    unlinked = [trace for trace in traces if trace not in (REMOTE_TRACE_ID, SECOND_TRACE_ID)]
    assert len(set(unlinked)) == 5


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


@dataclass
class _FakeRequestContext:
    request_id: object


def mcp_surface(hook: OpenTelemetryTracingHook) -> McpToolInvoker:
    app = Agnara("linked")
    registry = DIRegistry()

    @app.capability
    def ping() -> str:
        return "pong"

    mcp = Mcp(app)
    mcp.tool(ping)
    exposures = mcp.compile()
    plans = [
        ExecutionPlan.compile(app.capabilities[key], registry, hooks=[hook])
        for key in app.capabilities
    ]
    return McpToolInvoker(exposures, plans, DIContainer(registry))


async def mcp_call(invoker: McpToolInvoker, traceparent: str | None = None) -> Any:
    token = propagated(traceparent)
    try:
        return await invoker(
            cast("ServerRequestContext[Any]", _FakeRequestContext("req-1")),
            CallToolRequestParams(name="linked.ping", arguments={}),
        )
    finally:
        if token is not None:
            detach(token)


def test_an_mcp_capability_span_joins_a_propagated_caller_trace(spans: Any) -> None:
    hook, exporter = spans
    invoker = mcp_surface(hook)

    result = asyncio.run(mcp_call(invoker, REMOTE_TRACEPARENT))

    assert result.structured_content == {"result": "pong"}
    (span,) = exporter.get_finished_spans()
    assert span.context.trace_id == REMOTE_TRACE_ID
    assert parent_of(span) == REMOTE_SPAN_ID


def test_an_mcp_capability_span_is_a_root_without_propagation(spans: Any) -> None:
    hook, exporter = spans
    invoker = mcp_surface(hook)

    asyncio.run(mcp_call(invoker))

    (span,) = exporter.get_finished_spans()
    assert span.parent is None
    assert span.context.trace_id != REMOTE_TRACE_ID


# ---------------------------------------------------------------------------
# What the linked span may say
# ---------------------------------------------------------------------------


def test_joining_a_caller_trace_adds_no_transport_attribute(spans: Any) -> None:
    """Linking must not become a back door for transport data on a span."""
    hook, exporter = spans
    served = http_surface(hook)

    asyncio.run(http_request(served, REMOTE_TRACEPARENT))

    (span,) = exporter.get_finished_spans()
    assert span.attributes is not None
    assert set(span.attributes) == {"agnara.capability.id", "agnara.invocation.outcome"}
    assert "traceparent" not in span.to_json()


def test_the_capability_span_still_parents_its_own_nested_work(spans: Any) -> None:
    """A remote parent must not flatten in-process nesting from E9.3."""
    hook, exporter = spans
    registry = DIRegistry()

    inner = ExecutionPlan.compile(
        CapabilityDefinition(CapabilityId("tests", "inner"), lambda: "inner"),
        registry,
        hooks=[hook],
    )

    from agnara.execution import ExecutionContext, Invocation, invoke

    async def outer_handler() -> str:
        return str(
            await invoke(
                inner,
                ExecutionContext(
                    Invocation(capability_id=inner.definition.id, payload={}, metadata={}),
                    DIContainer(registry),
                ),
            )
        )

    outer = ExecutionPlan.compile(
        CapabilityDefinition(CapabilityId("tests", "outer"), outer_handler),
        registry,
        hooks=[hook],
    )
    served = _HTTPDispatcher(
        _compile_exposures([_HTTPExposure("GET", "/v1/show", outer)]),
        DIContainer(DIRegistry()),
        None,
    )

    asyncio.run(http_request(served, REMOTE_TRACEPARENT))

    inner_span, outer_span = exporter.get_finished_spans()
    assert outer_span.context.trace_id == REMOTE_TRACE_ID
    assert parent_of(outer_span) == REMOTE_SPAN_ID
    assert inner_span.context.trace_id == REMOTE_TRACE_ID
    assert parent_of(inner_span) == outer_span.context.span_id
