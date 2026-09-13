"""The HTTP server-sent events projection of a capability stream (ADR 0085).

The file is organized by the ADR's conformance matrix rather than by module,
because every row of that matrix is a promise to a client: what the response
looks like before any unit exists, what one unit becomes, and how a reader can
tell completion from failure without guessing.

Two properties get more attention than their size suggests. *Redaction*: an
exception or an oversized value must not reach the wire or the log, and the
tests use secret-shaped values so a regression is visible. *No false
atomicity*: once units have been sent, nothing may present the invocation as
though it produced nothing.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from agnara import Agnara
from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.core.di.resolver import DIContainer
from agnara.execution import (
    ExecutionPlan,
    InvocationStartEvent,
    InvocationTerminalEvent,
    TelemetryHook,
)
from agnara_http import Binding, BindingSource, Http, HttpDefinitionError, OpenApiOperation
from agnara_http._binding import _BindingDefinitionError, _BindingSource, _InputBinding
from agnara_http._dispatch import (
    _compile_exposures,
    _DispatchOptions,
    _HTTPDispatcher,
    _HTTPExposure,
    _OpenAPIPublication,
)
from agnara_http._sse import _SSEDefinitionError, _SSEProjection

CAPABILITY = CapabilityId("reports", "rows")


def plan(
    handler: Callable[..., Any],
    *,
    streaming: bool = True,
    registry: DIRegistry | None = None,
    hooks: tuple[TelemetryHook, ...] = (),
) -> ExecutionPlan:
    return ExecutionPlan.compile(
        CapabilityDefinition(CAPABILITY, handler, streaming=streaming),
        registry if registry is not None else DIRegistry(),
        hooks=hooks,
    )


def sse_exposure(
    handler: Callable[..., Any],
    *bindings: _InputBinding,
    path: str = "/reports",
    max_event_bytes: int = 1_048_576,
    registry: DIRegistry | None = None,
    hooks: tuple[TelemetryHook, ...] = (),
) -> _HTTPExposure:
    return _HTTPExposure(
        "GET",
        path,
        plan(handler, registry=registry, hooks=hooks),
        bindings,
        sse=_SSEProjection(max_event_bytes),
    )


def dispatcher(
    *exposures: _HTTPExposure,
    options: _DispatchOptions | None = None,
    registry: DIRegistry | None = None,
) -> _HTTPDispatcher:
    return _HTTPDispatcher(
        _compile_exposures(exposures),
        DIContainer(registry if registry is not None else DIRegistry()),
        options,
    )


class _Peer:
    """One connected client: what it received, and when it goes away.

    ``receive`` never returns on its own, which is what an SSE request really
    looks like: the body is complete and the only later message a server sees
    is a disconnect. A test calls `disconnect` to deliver one.
    """

    def __init__(self, *, fail_send_after: int | None = None) -> None:
        self.events: list[dict[str, Any]] = []
        self.body_sent = asyncio.Event()
        self._pending: list[dict[str, Any]] = [
            {"type": "http.request", "body": b"", "more_body": False}
        ]
        self._gate: asyncio.Future[dict[str, Any]] | None = None
        self._fail_send_after = fail_send_after
        self._bodies = 0

    async def receive(self) -> dict[str, Any]:
        if self._pending:
            return self._pending.pop(0)
        self._gate = asyncio.get_running_loop().create_future()
        return await self._gate

    def disconnect(self) -> None:
        message = {"type": "http.disconnect"}
        if self._gate is not None and not self._gate.done():
            self._gate.set_result(message)
        else:  # pragma: no cover - only if the watcher has not read yet
            self._pending.append(message)

    async def send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.body":
            self._bodies += 1
            if self._fail_send_after is not None and self._bodies > self._fail_send_after:
                raise OSError("connection reset by peer")
        self.events.append(message)
        self.body_sent.set()
        self.body_sent.clear()


async def serve(served: _HTTPDispatcher, peer: _Peer, *, path: str = "/reports") -> None:
    await served(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "root_path": "",
            "headers": [],
        },
        peer.receive,
        peer.send,
    )


def request(served: _HTTPDispatcher, *, path: str = "/reports") -> list[dict[str, Any]]:
    """Drive one complete SSE request and return the ASGI events it emitted."""
    peer = _Peer()

    async def run() -> None:
        await serve(served, peer, path=path)

    asyncio.run(run())
    return peer.events


def headers_of(events: list[dict[str, Any]]) -> dict[bytes, bytes]:
    return dict(events[0]["headers"])


def wire(events: list[dict[str, Any]]) -> str:
    """The complete response body as an SSE reader would see it."""
    return b"".join(event["body"] for event in events[1:]).decode("utf-8")


def data_units(events: list[dict[str, Any]]) -> list[Any]:
    """Every ``message`` event's JSON value, in order."""
    return [
        json.loads(block.removeprefix("data: "))
        for block in wire(events).split("\n\n")
        if block and not block.startswith("event:")
    ]


def terminal(events: list[dict[str, Any]]) -> dict[str, Any]:
    """The single ``agnara.terminal`` event, parsed."""
    blocks = [block for block in wire(events).split("\n\n") if block.startswith("event:")]
    assert len(blocks) == 1, blocks
    name, data = blocks[0].split("\n", 1)
    assert name == "event: agnara.terminal"
    return json.loads(data.removeprefix("data: "))


def problem(events: list[dict[str, Any]]) -> dict[str, Any]:
    return json.loads(events[1]["body"].decode("utf-8"))


# ---------------------------------------------------------------------------
# D1 -- SSE is an explicit exposure, checked when the surface compiles
# ---------------------------------------------------------------------------


def test_an_sse_exposure_must_target_a_streaming_capability() -> None:
    def rows() -> str:
        return "not a stream"

    with pytest.raises(_BindingDefinitionError, match="not declared streaming"):
        _compile_exposures(
            [_HTTPExposure("GET", "/reports", plan(rows, streaming=False), sse=_SSEProjection())]
        )


def test_an_ordinary_route_cannot_target_a_streaming_capability() -> None:
    """The complete JSON response boundary keeps its meaning (ADR 0027)."""

    async def rows() -> AsyncIterator[int]:
        yield 1

    with pytest.raises(_BindingDefinitionError, match="declared streaming"):
        _compile_exposures([_HTTPExposure("GET", "/reports", plan(rows))])


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_an_sse_exposure_is_get_only(method: str) -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1

    with pytest.raises(_BindingDefinitionError, match="GET-only"):
        _compile_exposures([_HTTPExposure(method, "/reports", plan(rows), sse=_SSEProjection())])


@pytest.mark.parametrize(
    "source",
    [_BindingSource.BODY, _BindingSource.FORM, _BindingSource.UPLOAD],
)
def test_an_sse_exposure_refuses_every_request_body_binding(source: _BindingSource) -> None:
    async def rows(command: str) -> AsyncIterator[int]:
        yield 1

    with pytest.raises(_BindingDefinitionError, match="reads no request body"):
        _compile_exposures(
            [
                _HTTPExposure(
                    "GET",
                    "/reports",
                    plan(rows),
                    (_InputBinding("command", source),),
                    sse=_SSEProjection(),
                )
            ]
        )


def test_an_sse_exposure_refuses_openapi_metadata() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1

    with pytest.raises(_BindingDefinitionError, match="no reviewed OpenAPI response schema"):
        _compile_exposures(
            [
                _HTTPExposure(
                    "GET",
                    "/reports",
                    plan(rows),
                    openapi=_OpenAPIPublication(summary="Rows"),
                    sse=_SSEProjection(),
                )
            ]
        )


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_the_per_event_ceiling_must_be_a_positive_integer(limit: Any) -> None:
    with pytest.raises(_SSEDefinitionError):
        _SSEProjection(limit)


def test_head_does_not_fall_back_to_an_sse_get() -> None:
    """A response with no body is not an honest read of a one-shot producer."""

    async def rows() -> AsyncIterator[int]:
        yield 1

    served = dispatcher(sse_exposure(rows))
    peer = _Peer()

    async def run() -> None:
        await served(
            {
                "type": "http",
                "method": "HEAD",
                "path": "/reports",
                "raw_path": b"/reports",
                "query_string": b"",
                "root_path": "",
                "headers": [],
            },
            peer.receive,
            peer.send,
        )

    asyncio.run(run())

    assert peer.events[0]["status"] == 405
    # `Allow` must not advertise the HEAD that the next request would refuse.
    assert headers_of(peer.events)[b"allow"] == b"GET"


# ---------------------------------------------------------------------------
# D2 -- one yielded value becomes one JSON `message` event
# ---------------------------------------------------------------------------


def test_each_unit_becomes_one_unnamed_message_event() -> None:
    async def rows() -> AsyncIterator[dict[str, int]]:
        yield {"row": 1}
        yield {"row": 2}

    events = request(dispatcher(sse_exposure(rows)))

    assert events[0]["status"] == 200
    assert headers_of(events) == {
        b"content-type": b"text/event-stream; charset=utf-8",
        b"cache-control": b"no-store",
    }
    assert b"content-length" not in headers_of(events)
    assert wire(events).startswith('data: {"row":1}\n\ndata: {"row":2}\n\n')
    assert data_units(events) == [{"row": 1}, {"row": 2}]


def test_no_id_or_retry_field_gives_last_event_id_a_meaning() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1

    body = wire(request(dispatcher(sse_exposure(rows))))

    assert "id:" not in body
    assert "retry:" not in body


def test_json_escaping_prevents_a_unit_from_injecting_an_sse_frame() -> None:
    """Newlines stay inside one JSON value, never becoming SSE syntax."""

    async def rows() -> AsyncIterator[str]:
        yield "line one\n\nevent: forged\ndata: forged\n☃"

    events = request(dispatcher(sse_exposure(rows)))

    assert data_units(events) == ["line one\n\nevent: forged\ndata: forged\n☃"]
    assert [line for line in wire(events).splitlines() if line.startswith("event:")] == [
        "event: agnara.terminal"
    ]


def test_a_unit_over_the_event_ceiling_is_refused_rather_than_truncated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def rows() -> AsyncIterator[str]:
        yield "first"
        yield "secret-" + "x" * 256

    served = dispatcher(sse_exposure(rows, max_event_bytes=64))
    with caplog.at_level(logging.ERROR, logger="agnara_http"):
        events = request(served)

    assert data_units(events) == ["first"]
    assert terminal(events) == {
        "outcome": "interrupted",
        "units": 1,
        "problem": {
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "code": "internal_failure",
            "detail": "The server could not complete the capability invocation.",
            "instance": "/reports",
        },
    }
    # The operator learns the location and the reason, never the value.
    assert "secret" not in caplog.text
    assert "over the 64 byte limit" in caplog.text


def test_a_first_unit_over_the_ceiling_keeps_the_ordinary_problem_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def rows() -> AsyncIterator[str]:
        yield "secret-" + "x" * 256

    served = dispatcher(sse_exposure(rows, max_event_bytes=64))
    with caplog.at_level(logging.ERROR, logger="agnara_http"):
        events = request(served)

    assert events[0]["status"] == 500
    assert headers_of(events)[b"content-type"] == b"application/problem+json"
    assert problem(events)["detail"] == "The server could not complete the capability invocation."
    assert "secret" not in caplog.text


def test_a_unit_the_json_boundary_cannot_represent_never_starts_a_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def rows() -> AsyncIterator[object]:
        yield object()

    with caplog.at_level(logging.ERROR, logger="agnara_http"):
        events = request(dispatcher(sse_exposure(rows)))

    assert events[0]["status"] == 500
    assert problem(events)["code"] == "internal_failure"


# ---------------------------------------------------------------------------
# D3 -- the response begins only after the first pull is representable
# ---------------------------------------------------------------------------


def test_a_policy_denial_before_output_is_an_ordinary_problem_response() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1  # pragma: no cover - policy runs first

    class Deny:
        async def evaluate(self, context: Any) -> Any:
            from agnara.policy import PolicyFailure

            return PolicyFailure("no viewer may read this report")

    denied = ExecutionPlan.compile(
        CapabilityDefinition(CAPABILITY, rows, streaming=True, policies=(Deny(),)),
        DIRegistry(),
    )
    served = dispatcher(
        _HTTPExposure("GET", "/reports", denied, sse=_SSEProjection()),
    )
    events = request(served)

    assert events[0]["status"] == 403
    assert headers_of(events)[b"content-type"] == b"application/problem+json"
    assert problem(events)["code"] == "forbidden"
    assert len(events) == 2


def test_a_missing_required_input_before_output_is_an_ordinary_problem_response() -> None:
    async def rows(report_id: int) -> AsyncIterator[int]:
        yield report_id  # pragma: no cover - binding fails first

    served = dispatcher(
        sse_exposure(rows, _InputBinding("report_id", _BindingSource.QUERY)),
    )
    events = request(served)

    assert events[0]["status"] == 400
    assert problem(events)["code"] == "invalid_input"


def test_a_producer_failing_on_the_first_pull_keeps_the_problem_response() -> None:
    """Zero units were exposed, so the ordinary HTTP failure is still honest."""

    async def rows() -> AsyncIterator[int]:
        raise RuntimeError("database password is hunter2")
        yield 1  # pragma: no cover - unreachable

    events = request(dispatcher(sse_exposure(rows)))

    assert events[0]["status"] == 500
    assert events[0]["headers"][0] == (b"content-type", b"application/problem+json")
    assert "hunter2" not in wire(events)
    assert problem(events)["detail"] == "The server could not complete the capability invocation."


def test_an_empty_producer_starts_the_response_and_states_that_it_completed() -> None:
    async def rows() -> AsyncIterator[int]:
        return
        yield 1  # pragma: no cover - unreachable

    events = request(dispatcher(sse_exposure(rows)))

    assert events[0]["status"] == 200
    assert data_units(events) == []
    assert terminal(events) == {"outcome": "completed", "units": 0}
    assert events[-1]["more_body"] is False


# ---------------------------------------------------------------------------
# D4 -- terminal events distinguish completion from a late failure
# ---------------------------------------------------------------------------


def test_normal_completion_reports_the_exact_unit_count() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1
        yield 2
        yield 3

    events = request(dispatcher(sse_exposure(rows)))

    assert data_units(events) == [1, 2, 3]
    assert terminal(events) == {"outcome": "completed", "units": 3}
    assert events[-1]["more_body"] is False


def test_a_producer_failure_after_output_is_not_presented_as_atomic() -> None:
    """No false atomicity: two rows reached the client and the wire says so."""

    async def rows() -> AsyncIterator[int]:
        yield 1
        yield 2
        raise RuntimeError("api key sk-live-secret expired")

    events = request(dispatcher(sse_exposure(rows)))

    assert events[0]["status"] == 200
    assert data_units(events) == [1, 2]
    ended = terminal(events)
    assert ended["outcome"] == "interrupted"
    assert ended["units"] == 2
    assert ended["problem"]["status"] == 500
    assert ended["problem"]["code"] == "internal_failure"
    assert "sk-live-secret" not in wire(events)


def test_a_deadline_after_output_ends_with_a_timeout_terminal() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1
        await asyncio.sleep(5)
        yield 2  # pragma: no cover - the deadline arrives first

    served = dispatcher(
        sse_exposure(rows),
        options=_DispatchOptions(timeout=0.05),
    )
    events = request(served)

    assert data_units(events) == [1]
    ended = terminal(events)
    assert ended["outcome"] == "timed_out"
    assert ended["units"] == 1
    assert ended["problem"]["status"] == 504
    assert ended["problem"]["code"] == "timeout"


def test_a_deadline_before_output_is_an_ordinary_gateway_timeout() -> None:
    async def rows() -> AsyncIterator[int]:
        await asyncio.sleep(5)
        yield 1  # pragma: no cover - the deadline arrives first

    served = dispatcher(sse_exposure(rows), options=_DispatchOptions(timeout=0.05))
    events = request(served)

    assert events[0]["status"] == 504
    assert problem(events)["code"] == "timeout"


def test_a_configured_problem_base_uri_reaches_the_terminal_event() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("boom")

    served = dispatcher(
        sse_exposure(rows),
        options=_DispatchOptions(problem_types=_problem_types()),
    )
    events = request(served)

    assert terminal(events)["problem"]["type"] == "https://errors.example/internal-failure"


def _problem_types() -> Any:
    from agnara_http._problem import _compile_problem_types

    return _compile_problem_types("https://errors.example/")


# ---------------------------------------------------------------------------
# D5 -- send demand is the stream's demand, and disconnect is owned
# ---------------------------------------------------------------------------


def test_sse_uses_one_canonical_telemetry_lifecycle() -> None:
    class Recorder(TelemetryHook):
        def __init__(self) -> None:
            self.starts: list[InvocationStartEvent] = []
            self.terminals: list[InvocationTerminalEvent] = []

        def on_invocation_start(self, event: InvocationStartEvent) -> None:
            self.starts.append(event)

        def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
            self.terminals.append(event)

    async def rows() -> AsyncIterator[int]:
        yield 1
        yield 2

    recorder = Recorder()
    events = request(dispatcher(sse_exposure(rows, hooks=(recorder,))))

    assert data_units(events) == [1, 2]
    [start] = recorder.starts
    [ended] = recorder.terminals
    assert ended.invocation_id == start.invocation_id
    assert ended.outcome == "completed"
    assert ended.units == 2


def test_a_slow_client_slows_the_producer() -> None:
    """One pull per completed send: nothing accumulates in the adapter."""
    produced: list[int] = []
    released = asyncio.Event()

    async def rows() -> AsyncIterator[int]:
        for value in range(1, 4):
            produced.append(value)
            yield value

    async def run() -> None:
        peer = _Peer()
        original = peer.send
        first = True

        async def slow(message: dict[str, Any]) -> None:
            nonlocal first
            if message["type"] == "http.response.body" and first:
                first = False
                await released.wait()
            await original(message)

        peer.send = slow  # ty: ignore[invalid-assignment]
        served = dispatcher(sse_exposure(rows))
        task = asyncio.create_task(serve(served, peer))
        await asyncio.sleep(0.02)

        # The first send has not returned, so the producer is one unit ahead
        # and not three: there is no queue behind the consumer.
        assert produced == [1]
        released.set()
        await task
        assert produced == [1, 2, 3]

    asyncio.run(run())


def test_a_client_disconnect_cancels_the_producer_and_promises_no_terminal() -> None:
    cleaned = False

    async def rows() -> AsyncIterator[int]:
        nonlocal cleaned
        try:
            yield 1
            await asyncio.sleep(5)
            yield 2  # pragma: no cover - cancelled first
        finally:
            cleaned = True

    async def run() -> None:
        peer = _Peer()
        served = dispatcher(sse_exposure(rows))
        task = asyncio.create_task(serve(served, peer))
        await asyncio.sleep(0.02)
        peer.disconnect()
        await task

        assert data_units(peer.events) == [1]
        assert "agnara.terminal" not in wire(peer.events)
        assert cleaned is True
        # The watcher was joined, not abandoned.
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())


def test_a_send_failure_closes_the_stream_without_logging_a_server_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cleaned = False

    async def rows() -> AsyncIterator[int]:
        nonlocal cleaned
        try:
            yield 1
            yield 2
            yield 3  # pragma: no cover - the peer is gone first
        finally:
            cleaned = True

    async def run() -> None:
        peer = _Peer(fail_send_after=1)
        served = dispatcher(sse_exposure(rows))
        with caplog.at_level(logging.ERROR, logger="agnara_http"):
            await serve(served, peer)

        assert data_units(peer.events) == [1]
        assert "agnara.terminal" not in wire(peer.events)
        assert cleaned is True
        assert caplog.records == []
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())


def test_application_cancellation_propagates_instead_of_becoming_a_terminal() -> None:
    cleaned = False

    async def rows() -> AsyncIterator[int]:
        nonlocal cleaned
        try:
            yield 1
            await asyncio.sleep(5)
            yield 2  # pragma: no cover - cancelled first
        finally:
            cleaned = True

    async def run() -> None:
        peer = _Peer()
        served = dispatcher(sse_exposure(rows))
        task = asyncio.create_task(serve(served, peer))
        await asyncio.sleep(0.02)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert "agnara.terminal" not in wire(peer.events)
        assert cleaned is True
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())


# ---------------------------------------------------------------------------
# D6 -- no accidental OpenAPI or discovery promise
# ---------------------------------------------------------------------------


def test_an_sse_route_is_absent_from_the_openapi_document() -> None:
    app = Agnara("reports")

    @app.capability(streaming=True)
    async def rows() -> AsyncIterator[int]:
        yield 1

    @app.capability
    def health() -> str:
        return "ok"

    from agnara_http import OpenApiInfo

    http = Http()
    http.sse("/reports", rows)
    http.get("/health", health, openapi=OpenApiOperation(summary="Health"))
    compiled = http.compile(app.compile(), openapi=OpenApiInfo("Reports", "1.0"))

    assert list(compiled.openapi()["paths"]) == ["/health"]


# ---------------------------------------------------------------------------
# The public composition API
# ---------------------------------------------------------------------------


def test_the_public_declaration_serves_a_stream_end_to_end() -> None:
    app = Agnara("reports")

    @app.capability(streaming=True, output=int)
    async def rows(report_id: int) -> AsyncIterator[int]:
        for offset in range(report_id, report_id + 2):
            yield offset

    http = Http()
    http.sse("/reports/{report_id}", rows, Binding("report_id", BindingSource.PATH))
    compiled = http.compile(app.compile())

    peer = _Peer()

    async def run() -> None:
        await compiled(
            {
                "type": "http",
                "method": "GET",
                "path": "/reports/7",
                "raw_path": b"/reports/7",
                "query_string": b"",
                "root_path": "",
                "headers": [],
            },
            peer.receive,
            peer.send,
        )

    asyncio.run(run())

    assert data_units(peer.events) == [7, 8]
    assert terminal(peer.events) == {"outcome": "completed", "units": 2}


def test_an_ordinary_public_route_refuses_a_streaming_capability() -> None:
    app = Agnara("reports")

    @app.capability(streaming=True)
    async def rows() -> AsyncIterator[int]:
        yield 1

    http = Http()
    http.get("/reports", rows)

    with pytest.raises(HttpDefinitionError, match=r"declare it with Http.sse"):
        http.compile(app.compile())


def test_the_public_declaration_refuses_a_body_binding() -> None:
    app = Agnara("reports")

    @app.capability(streaming=True)
    async def rows(command: str) -> AsyncIterator[str]:
        yield command

    http = Http()
    http.sse("/reports", rows, Binding("command", BindingSource.BODY))

    with pytest.raises(HttpDefinitionError, match="reads no request body"):
        http.compile(app.compile())


def test_the_public_declaration_validates_its_event_ceiling() -> None:
    app = Agnara("reports")

    @app.capability(streaming=True)
    async def rows() -> AsyncIterator[int]:
        yield 1

    http = Http()
    with pytest.raises(HttpDefinitionError, match="max_event_bytes"):
        http.sse("/reports", rows, max_event_bytes="big")  # ty: ignore[invalid-argument-type]


def test_a_declared_output_violation_reaches_the_wire_redacted() -> None:
    """ADR 0086 and ADR 0085 agree on what a caller learns: nothing."""
    app = Agnara("reports")

    @app.capability(streaming=True, output=int)
    async def rows() -> AsyncIterator[Any]:
        yield 1
        yield "secret report content"

    http = Http()
    http.sse("/reports", rows)
    compiled = http.compile(app.compile())

    peer = _Peer()

    async def run() -> None:
        await compiled(
            {
                "type": "http",
                "method": "GET",
                "path": "/reports",
                "raw_path": b"/reports",
                "query_string": b"",
                "root_path": "",
                "headers": [],
            },
            peer.receive,
            peer.send,
        )

    asyncio.run(run())

    assert data_units(peer.events) == [1]
    ended = terminal(peer.events)
    assert ended["outcome"] == "interrupted"
    assert ended["units"] == 1
    assert "secret report content" not in wire(peer.events)
