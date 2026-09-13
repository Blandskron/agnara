"""The HTTP Server-Sent Events projection of an owned capability stream.

ADR 0085 decides this wire; this module is the whole of it. Three properties
are what the decision is actually about, and each is visible here:

* **The response starts late.** Policy, binding, validation, dependencies and
  the first pull all happen before ``http.response.start``, so a failure with
  zero exposed units is still an ordinary RFC 9457 problem response (D3).
* **Demand is the client's.** One pull, one encode, one awaited send, in that
  order and never overlapped. A slow peer slows the producer and the adapter
  holds at most one encoded event (D2, D5).
* **The end is stated, not inferred.** A closed connection cannot distinguish
  exhaustion from failure, so a started response always tries to end with the
  ``agnara.terminal`` event carrying the outcome, the exact unit count and, for
  a failure after output, the redacted problem document (D4).

No SSE, ASGI or HTTP vocabulary travels back into `agnara`: this consumes the
neutral `CapabilityStream` and the canonical failure classifier, and invents no
unit or failure semantics of its own.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from agnara.capability import CapabilityId
from agnara.execution import (
    CapabilityStream,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    StreamInterrupted,
    StreamTerminal,
    classify_failure,
    open_stream,
)
from agnara.schema import materialize_json
from agnara_http._problem import (
    _ABOUT_BLANK_TYPES,
    _INTERNAL_PROBLEM,
    _failure_document,
    _serialize_failure,
)
from agnara_http._response import (
    _ResponseSerializationError,
    _send_response,
    _to_json_value,
)

type _Message = dict[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]
type _Send = Callable[[_Message], Awaitable[None]]

_LOGGER = logging.getLogger("agnara_http")

#: The response representation. ``no-store`` because a capability stream is an
#: execution, not a cacheable document; nothing else here is the adapter's to
#: decide (ADR 0072 leaves compression, CORS and proxy buffering outside).
_SSE_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-type", b"text/event-stream; charset=utf-8"),
    (b"cache-control", b"no-store"),
)

#: The one adapter-owned event name. Data events deliberately carry no name so
#: an ``EventSource`` consumer receives the standard ``message`` event.
_TERMINAL_EVENT_NAME = b"event: agnara.terminal\n"

#: Same ceiling as the request body limit. A unit larger than this is a
#: projection failure, never a reason to truncate or drop application data.
_DEFAULT_MAX_EVENT_BYTES = 1_048_576

#: What an unexpected producer failure is allowed to say on the wire. Built
#: from the canonical redacted failure so the SSE terminal and an ordinary
#: HTTP response cannot disagree about what a caller learns.
_REDACTED_FAILURE = Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")


class _SSEDefinitionError(ValueError):
    """An SSE exposure is not one this projection can serve truthfully."""


@dataclass(frozen=True, slots=True)
class _SSEProjection:
    """The SSE representation contract of one compiled exposure."""

    max_event_bytes: int = _DEFAULT_MAX_EVENT_BYTES

    def __post_init__(self) -> None:
        if isinstance(self.max_event_bytes, bool) or not isinstance(self.max_event_bytes, int):
            raise _SSEDefinitionError("max_event_bytes must be an integer")
        if self.max_event_bytes <= 0:
            raise _SSEDefinitionError("max_event_bytes must be a positive number of bytes")


@dataclass(frozen=True, slots=True)
class _SSERequest:
    """Everything the projection needs that is not the stream itself."""

    projection: _SSEProjection
    capability_id: CapabilityId
    target: str
    problem_types: Mapping[str, str] = _ABOUT_BLANK_TYPES
    instance: str | None = None


async def _serve_sse(
    plan: ExecutionPlan,
    context: ExecutionContext,
    request: _SSERequest,
    receive: _Receive,
    send: _Send,
) -> None:
    """Serve one SSE response for one streaming capability invocation.

    The stream is opened, drained and closed by this task and no other, which
    is the ownership ADR 0084 requires of any consumer. The disconnect watcher
    below is a separate task on purpose, but it only ever *cancels* this one:
    it never touches the stream.
    """
    consumer = asyncio.current_task()
    if consumer is None:  # pragma: no cover - ASGI always runs inside a task
        raise RuntimeError("the SSE projection must run inside an asyncio task")

    stream = open_stream(plan, context, input_materializer=materialize_json)
    async with contextlib.AsyncExitStack() as scope:
        try:
            await scope.enter_async_context(stream)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Pre-output (ADR 0085 D3). Policy, materialization, validation and
            # dependency construction all failed before anything was exposed,
            # so the ordinary complete problem response is still the honest
            # answer, classified by the rule every other boundary uses.
            await _send_response(
                _serialize_failure(
                    classify_failure(error, request.capability_id),
                    problem_types=request.problem_types,
                    instance=request.instance,
                ),
                send,
            )
            return

        wire = await _start_response(stream, request, send)
        if wire is None:
            return

        watch = _DisconnectWatch(receive, consumer)
        try:
            async with watch:
                await _pump(stream, wire)
        except asyncio.CancelledError:
            if watch.seen and consumer.uncancel() == 0:
                # The peer is gone and nothing else cancelled us. Unwinding
                # this scope closes the producer; no terminal can be promised
                # to a connection that no longer exists (ADR 0085 D4).
                return
            raise


class _SSEWire:
    """The started response: it owns the wire and counts what reached the peer."""

    __slots__ = ("_send", "request", "units")

    def __init__(self, send: _Send, request: _SSERequest) -> None:
        self._send = send
        self.request = request
        self.units = 0

    async def send_event(self, event: bytes) -> bool:
        """Send one data event, reporting whether the peer is still there.

        Returning rather than raising on `OSError` is deliberate: a peer that
        closed mid-response is an expected end, not a server error, and it must
        not be logged as one.
        """
        try:
            await self._send({"type": "http.response.body", "body": event, "more_body": True})
        except OSError:
            return False
        self.units += 1
        return True

    async def send_terminal(
        self,
        terminal: StreamTerminal,
        problem: Mapping[str, Any] | None,
    ) -> None:
        """Close the response with the one event that states how it ended."""
        document: dict[str, Any] = {"outcome": terminal.value, "units": self.units}
        if problem is not None:
            document["problem"] = dict(problem)
        event = _TERMINAL_EVENT_NAME + b"data: " + _encode(document) + b"\n\n"
        with contextlib.suppress(OSError):
            await self._send({"type": "http.response.body", "body": event, "more_body": False})

    def problem(self, failure: Failure) -> dict[str, Any]:
        """The redacted RFC 9457 projection this terminal event may carry."""
        return _failure_document(
            failure,
            problem_types=self.request.problem_types,
            instance=self.request.instance,
        )


async def _start_response(
    stream: CapabilityStream,
    request: _SSERequest,
    send: _Send,
) -> _SSEWire | None:
    """Pull and encode the first unit, then begin the response, or answer 9457.

    ``None`` means the response never began and a complete problem response was
    sent instead. That is the whole reason the first pull happens here: until
    one unit is representable, the ordinary HTTP failure boundary is still
    available and is a better answer than a 200 that immediately breaks.
    """
    first: bytes | None
    try:
        unit = await anext(stream)
    except StopAsyncIteration:
        # An empty producer is a successful first result, not an absent one.
        first = None
    except StreamInterrupted as interrupted:
        await _send_response(
            _serialize_failure(
                interrupted.failure,
                problem_types=request.problem_types,
                instance=request.instance,
            ),
            send,
        )
        return None
    else:
        try:
            first = _data_event(unit, request.projection.max_event_bytes)
        except (_ResponseSerializationError, RecursionError) as error:
            _log_unrepresentable(request, error)
            await _send_response(_INTERNAL_PROBLEM, send)
            return None

    await send({"type": "http.response.start", "status": 200, "headers": list(_SSE_HEADERS)})
    wire = _SSEWire(send, request)
    if first is not None and not await wire.send_event(first):
        return None
    return wire


async def _pump(stream: CapabilityStream, wire: _SSEWire) -> None:
    """Pull, encode and send one unit at a time until the stream ends.

    One pull per completed send, with nothing in between: that ordering is what
    makes ASGI send demand the producer's demand (ADR 0085 D5).
    """
    problem: dict[str, Any] | None = None
    while True:
        try:
            unit = await anext(stream)
        except StopAsyncIteration:
            terminal = StreamTerminal.COMPLETED
            break
        except StreamInterrupted as interrupted:
            # Units already reached the peer, so this cannot become a status
            # line. It becomes data inside the terminal event (ADR 0085 D4).
            terminal = stream.terminal or StreamTerminal.INTERRUPTED
            problem = wire.problem(interrupted.failure)
            break

        try:
            event = _data_event(unit, wire.request.projection.max_event_bytes)
        except (_ResponseSerializationError, RecursionError) as error:
            _log_unrepresentable(wire.request, error)
            terminal = StreamTerminal.INTERRUPTED
            problem = wire.problem(_REDACTED_FAILURE)
            break

        if not await wire.send_event(event):
            # The peer is gone: there is nobody left to tell how it ended.
            return

    await wire.send_terminal(terminal, problem)


class _DisconnectWatch:
    """Cancel the response pump when the peer goes away (ADR 0085 D5).

    One task, created when the response starts and cancelled and joined before
    this scope exits. An unowned reader would turn a client close into a leaked
    producer, which is the ownership rule ADR 0084 exists to hold.

    It cancels rather than signals because cancellation is the one mechanism
    that reaches a pump blocked in `anext` or in `send` without a second
    consumer of either.
    """

    __slots__ = ("_consumer", "_receive", "_task", "seen")

    def __init__(self, receive: _Receive, consumer: asyncio.Task[Any]) -> None:
        self._receive = receive
        self._consumer = consumer
        self._task: asyncio.Task[None] | None = None
        self.seen = False

    async def __aenter__(self) -> _DisconnectWatch:
        self._task = asyncio.create_task(self._watch())
        return self

    async def _watch(self) -> None:
        while True:
            message = await self._receive()
            if isinstance(message, Mapping) and message.get("type") == "http.disconnect":
                self.seen = True
                self._consumer.cancel()
                return

    async def __aexit__(self, *_: object) -> bool:
        task = self._task
        self._task = None
        if task is None:  # pragma: no cover - the scope is entered before use
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            if self._consumer.cancelling():
                # This task was cancelled too, in the instant before the
                # watcher was stopped. That cancellation is not ours to eat.
                raise
        return False


def _data_event(unit: object, max_event_bytes: int) -> bytes:
    """Encode one yielded unit as one complete ``message`` event.

    The unit travels through the same JSON value rule every other HTTP
    response uses, so a stream cannot represent something a complete result
    could not.
    """
    encoded = _encode(_to_json_value(unit, path="$"))
    event = b"data: " + encoded + b"\n\n"
    if len(event) > max_event_bytes:
        raise _ResponseSerializationError(
            f"the encoded event is {len(event)} bytes, over the {max_event_bytes} byte limit"
        )
    return event


def _encode(value: Any) -> bytes:
    """One compact, deterministic UTF-8 JSON value, as ADR 0085 D2 requires."""
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise _ResponseSerializationError("stream unit is not valid UTF-8 JSON") from error


def _log_unrepresentable(request: _SSERequest, error: Exception) -> None:
    """Report an operational diagnostic that never carries the value itself."""
    _LOGGER.error(
        "%s: the capability %s produced a unit this SSE response cannot carry: %s",
        request.target,
        request.capability_id,
        error,
    )
