"""V1-29 evidence for one host-owned OpenTelemetry pipeline."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, MutableMapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry.context import attach, detach
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from agnara import Agnara, App, Principal
from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    IdempotencyInvocation,
    IdempotencyScope,
    InMemoryIdempotencyStore,
    Invocation,
    StreamInterrupted,
    Success,
    open_stream,
)
from agnara_telemetry import OpenTelemetryTracingHook

_REMOTE_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
_REMOTE_TRACE_ID = 0x4BF92F3577B34DA6A3CE929D0E0E4736
_SECRET_PAYLOAD = "payload-must-not-export"
_SECRET_CREDENTIAL = "credential-must-not-export"
_SECRET_RESULT = "stored-result-must-not-export"
_OUTER = CapabilityId.parse("telemetry.outer")
_INNER = CapabilityId.parse("telemetry.inner")
_STORED = CapabilityId.parse("telemetry.stored")
_STREAM = CapabilityId.parse("telemetry.stream")


@dataclass
class HostState:
    runtime: CapabilityRuntime | None = None
    container: DIContainer | None = None


class JsonCodec:
    def encode(self, value: object, /) -> bytes:
        return json.dumps(value, sort_keys=True).encode("utf-8")

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


@pytest.fixture
def traced() -> Iterator[tuple[Tracer, InMemorySpanExporter]]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    try:
        yield provider.get_tracer("v1-29"), exporter
    finally:
        provider.shutdown()


def _runtime(tracer: Tracer) -> tuple[CapabilityRuntime, DIContainer]:
    project, app = Agnara("telemetry"), App("telemetry")
    hook = OpenTelemetryTracingHook(tracer)

    @app.capability
    def inner(value: str) -> str:
        return f"inner:{value}"

    @app.capability
    async def outer(value: str, invoker: CapabilityInvoker) -> str:
        result = await invoker.invoke(_INNER, {"value": value})
        assert isinstance(result, Success)
        return f"outer:{result.value}"

    @app.capability(idempotent=True)
    def stored(value: str) -> dict[str, str]:
        assert value == _SECRET_PAYLOAD
        return {"receipt": _SECRET_RESULT}

    project.include(app)
    capabilities = project.compile()
    registry = DIRegistry()
    plans = [
        ExecutionPlan.compile(capability, registry, hooks=[hook])
        for capability in capabilities.values()
    ]
    container = DIContainer(registry)
    return CapabilityRuntime(capabilities, plans, container), container


def _context(
    capability_id: CapabilityId,
    container: DIContainer,
    payload: dict[str, object],
    *,
    principal: Principal | None = None,
    idempotency: IdempotencyInvocation | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        Invocation(capability_id, payload, {"credential": _SECRET_CREDENTIAL}),
        container,
        tracking_id=_SECRET_CREDENTIAL,
        principal=principal,
        idempotency=idempotency,
    )


async def _request(
    app: FastAPI, path: str, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    sent: list[dict[str, Any]] = []
    sent_request = False

    async def receive() -> dict[str, Any]:
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(dict(message))

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(key.encode(), value.encode()) for key, value in (headers or {}).items()],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    return {
        "status": start["status"],
        "body": b"".join(message.get("body", b"") for message in sent),
    }


def _host(tracer: Tracer) -> tuple[FastAPI, HostState]:
    state = HostState()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state.runtime, state.container = _runtime(tracer)
        try:
            yield
        finally:
            assert state.runtime is not None
            await state.runtime.aclose()
            state.runtime = None
            state.container = None

    host = FastAPI(lifespan=lifespan)

    async def within_host_span(
        request: Request,
        name: str,
        operation: Callable[[], Awaitable[Success[object]]],
    ) -> Success[object]:
        # Extraction and the SERVER span are host instrumentation. Neither
        # reaches Agnara as a request, span, metadata field, or DI binding.
        token = attach(TraceContextTextMapPropagator().extract(dict(request.headers)))
        try:
            with tracer.start_as_current_span(name, kind=SpanKind.SERVER):
                return await operation()
        finally:
            detach(token)

    @host.get("/native")
    async def native(request: Request) -> JSONResponse:
        async def operation() -> Success[object]:
            return Success({"owner": "host"})

        result = await within_host_span(request, "host.native", operation)
        return JSONResponse(result.value)

    @host.get("/compose/{value}")
    async def compose(value: str, request: Request) -> JSONResponse:
        assert state.runtime is not None and state.container is not None

        runtime, container = state.runtime, state.container
        assert runtime is not None and container is not None

        async def operation() -> Success[object]:
            return cast(
                Success[object],
                await runtime.invoke_result(_context(_OUTER, container, {"value": value})),
            )

        result = await within_host_span(request, "host.compose", operation)
        return JSONResponse({"value": result.value})

    return host, state


def _spans(exporter: InMemorySpanExporter) -> tuple[ReadableSpan, ...]:
    return exporter.get_finished_spans()


def _by_name(exporter: InMemorySpanExporter, name: str) -> ReadableSpan:
    matches = [span for span in _spans(exporter) if span.name == name]
    assert len(matches) == 1
    return matches[0]


def test_fastapi_host_and_nested_capabilities_share_one_trace_without_duplicate_ownership(
    traced: tuple[Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = traced
    host, state = _host(tracer)

    async def run() -> None:
        async with host.router.lifespan_context(host):
            response = await _request(host, "/compose/value", {"traceparent": _REMOTE_TRACEPARENT})
            assert response == {"status": 200, "body": b'{"value":"outer:inner:value"}'}
            native = await _request(host, "/native", {"traceparent": _REMOTE_TRACEPARENT})
            assert native == {"status": 200, "body": b'{"owner":"host"}'}
        assert state.runtime is None and state.container is None

    asyncio.run(run())

    host_span = _by_name(exporter, "host.compose")
    outer_span = _by_name(exporter, str(_OUTER))
    inner_span = _by_name(exporter, str(_INNER))
    assert {
        host_span.context.trace_id,
        outer_span.context.trace_id,
        inner_span.context.trace_id,
    } == {_REMOTE_TRACE_ID}
    assert host_span.parent is not None
    assert outer_span.parent is not None and outer_span.parent.span_id == host_span.context.span_id
    assert inner_span.parent is not None and inner_span.parent.span_id == outer_span.context.span_id
    assert len([span for span in _spans(exporter) if span.name == "host.compose"]) == 1

    assert outer_span.attributes is not None and inner_span.attributes is not None
    assert (
        outer_span.attributes["agnara.execution.id"]
        != outer_span.attributes["agnara.invocation.id"]
    )
    assert (
        inner_span.attributes["agnara.parent_execution.id"]
        == outer_span.attributes["agnara.execution.id"]
    )
    assert (
        inner_span.attributes["agnara.execution.id"] != outer_span.attributes["agnara.execution.id"]
    )
    rendered = "\n".join(span.to_json() for span in _spans(exporter))
    assert _SECRET_CREDENTIAL not in rendered
    assert "traceparent" not in rendered


def test_parallel_host_requests_keep_remote_trace_context_isolated(
    traced: tuple[Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = traced
    host, _ = _host(tracer)
    other = "00-1234567890abcdef1234567890abcdef-00f067aa0ba902b8-01"
    other_id = 0x1234567890ABCDEF1234567890ABCDEF

    async def run() -> None:
        async with host.router.lifespan_context(host):
            responses = await asyncio.gather(
                *(
                    _request(host, f"/compose/{index}", {"traceparent": traceparent})
                    for index, traceparent in enumerate((_REMOTE_TRACEPARENT, other) * 8)
                )
            )
            assert all(response["status"] == 200 for response in responses)

    asyncio.run(run())

    spans = _spans(exporter)
    assert len(spans) == 48  # host + outer + inner for each request
    assert sum(span.context.trace_id == _REMOTE_TRACE_ID for span in spans) == 24
    assert sum(span.context.trace_id == other_id for span in spans) == 24
    assert all(span.name in {"host.compose", str(_OUTER), str(_INNER)} for span in spans)


def test_tracing_redacts_payload_claims_credentials_and_idempotent_results(
    traced: tuple[Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = traced
    runtime, container = _runtime(tracer)
    store = InMemoryIdempotencyStore()
    actor = Principal("actor", metadata={"claim": _SECRET_CREDENTIAL})
    idempotency = IdempotencyInvocation(
        IdempotencyScope(_STORED, actor.identity, "fixture-key", b"fixture-fingerprint"),
        store,
        JsonCodec(),
        30,
        60,
    )

    async def run() -> None:
        with tracer.start_as_current_span("host.store", kind=SpanKind.SERVER):
            first = await runtime.invoke_result(
                _context(
                    _STORED,
                    container,
                    {"value": _SECRET_PAYLOAD},
                    principal=actor,
                    idempotency=idempotency,
                )
            )
            second = await runtime.invoke_result(
                _context(
                    _STORED,
                    container,
                    {"value": _SECRET_PAYLOAD},
                    principal=actor,
                    idempotency=idempotency,
                )
            )
            assert first == second == Success({"receipt": _SECRET_RESULT})
        await runtime.aclose()

    asyncio.run(run())

    rendered = "\n".join(span.to_json() for span in _spans(exporter))
    for secret in (
        _SECRET_PAYLOAD,
        _SECRET_CREDENTIAL,
        _SECRET_RESULT,
        "fixture-key",
        "fixture-fingerprint",
    ):
        assert secret not in rendered
    assert len([span for span in _spans(exporter) if span.name == str(_STORED)]) == 2


def test_host_stream_spans_end_once_for_completion_late_failure_and_cancellation(
    traced: tuple[Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = traced
    hook = OpenTelemetryTracingHook(tracer)
    registry = DIRegistry()
    entered = asyncio.Event()

    async def complete() -> AsyncIterator[str]:
        yield "one"

    async def fail_late() -> AsyncIterator[str]:
        yield "one"
        raise RuntimeError(_SECRET_RESULT)

    async def wait_for_cancel() -> AsyncIterator[str]:
        entered.set()
        await asyncio.Event().wait()
        yield "never"

    def plan(handler: Callable[[], AsyncIterator[str]]) -> ExecutionPlan:
        return ExecutionPlan.compile(
            CapabilityDefinition(_STREAM, handler, streaming=True), registry, hooks=[hook]
        )

    async def consume(plan: ExecutionPlan, name: str) -> list[str]:
        context = _context(plan.definition.id, DIContainer(registry), {})
        with tracer.start_as_current_span(name, kind=SpanKind.SERVER):
            async with open_stream(plan, context) as stream:
                units = [str(unit) async for unit in stream]
        return units

    async def run() -> None:
        complete_plan, failure_plan, cancellation_plan = (
            plan(complete),
            plan(fail_late),
            plan(wait_for_cancel),
        )
        assert await consume(complete_plan, "host.stream.complete") == ["one"]
        with pytest.raises(StreamInterrupted) as interrupted:
            await consume(failure_plan, "host.stream.failure")
        assert interrupted.value.units_emitted == 1
        task = asyncio.create_task(consume(cancellation_plan, "host.stream.cancel"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())

    stream_spans = [span for span in _spans(exporter) if span.name == str(_STREAM)]
    assert len(stream_spans) == 3
    assert [
        span.attributes["agnara.invocation.outcome"] for span in stream_spans if span.attributes
    ] == [
        "success",
        "failure",
        "cancellation",
    ]
    assert all(span.end_time is not None for span in stream_spans)
    rendered = "\n".join(span.to_json() for span in stream_spans)
    assert _SECRET_RESULT not in rendered


#: Run in a fresh interpreter: this process has already imported the SDK for
#: the fixtures above, so an in-process check would prove nothing. The finder
#: raises rather than returning ``None`` so a lazy import inside a kernel code
#: path fails loudly instead of falling through to a real installed package.
_ABSENT_OPENTELEMETRY = """
import asyncio
import sys


class _AbsentOpenTelemetry:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "opentelemetry" or fullname.startswith("opentelemetry."):
            raise ModuleNotFoundError(fullname, name=fullname)
        return None


sys.meta_path.insert(0, _AbsentOpenTelemetry())

from agnara import Agnara, App
from agnara.capability import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
    open_stream,
)

project, app = Agnara("absent"), App("absent")


@app.capability
def inner(value: str) -> str:
    return f"inner:{value}"


@app.capability
async def outer(value: str, invoker: CapabilityInvoker) -> str:
    result = await invoker.invoke(CapabilityId.parse("absent.inner"), {"value": value})
    assert isinstance(result, Success)
    return f"outer:{result.value}"


@app.capability(streaming=True)
async def ticks():
    yield "one"
    yield "two"


project.include(app)
capabilities = project.compile()
registry = DIRegistry()
plans = [ExecutionPlan.compile(capability, registry) for capability in capabilities.values()]
container = DIContainer(registry)
runtime = CapabilityRuntime(capabilities, plans, container)


async def main() -> None:
    nested = await runtime.invoke_result(
        ExecutionContext(
            Invocation(CapabilityId.parse("absent.outer"), {"value": "value"}, {}), container
        )
    )
    assert nested == Success("outer:inner:value"), nested
    stream_plan = next(plan for plan in plans if str(plan.definition.id) == "absent.ticks")
    context = ExecutionContext(
        Invocation(CapabilityId.parse("absent.ticks"), {}, {}), container
    )
    async with open_stream(stream_plan, context) as stream:
        assert [str(unit) async for unit in stream] == ["one", "two"]
    await runtime.aclose()


asyncio.run(main())

leaked = sorted(name for name in sys.modules if name.split(".")[0] == "opentelemetry")
assert not leaked, leaked
print("ran without opentelemetry")
"""


def test_core_compiles_and_runs_with_opentelemetry_absent_from_the_environment() -> None:
    """The bridge is optional, so the kernel must not need the package at all.

    The architecture suite already proves no core distribution *declares* or
    *names* an OpenTelemetry import. That is a static guarantee; this one is
    behavioural. Compilation, nested invocation and streaming all execute in an
    interpreter where importing ``opentelemetry`` raises, which is the shape an
    application without the bridge installed actually runs in.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _ABSENT_OPENTELEMETRY],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "ran without opentelemetry" in completed.stdout
