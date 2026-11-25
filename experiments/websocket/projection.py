"""ASGI 3.0 WebSocket streaming projection prototype (RFC 0013 / WS-01).

Uses only Python's standard library and canonical public ``agnara`` APIs to
measure pre-accept origin/policy rejection, handshake vs. initial-frame inputs,
pull-based backpressure, disconnect cancellation, and same-loop DI cleanup.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qsl

from agnara import Principal
from agnara.di import DIContainer
from agnara.execution import (
    CapabilityStream,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    StreamInterrupted,
    StreamTerminal,
    classify_failure,
    open_stream,
)
from agnara.schema import materialize_json, serialize_json

type _Scope = dict[str, Any]
type _Message = dict[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]
type _Send = Callable[[_Message], Awaitable[None]]

_REDACTED_ERROR: dict[str, str] = {
    "code": FailureCode.INTERNAL_FAILURE.value,
    "message": "capability invocation failed",
}

_INTERNAL_CLOSE_CODES = frozenset(
    {
        FailureCode.INTERNAL_FAILURE,
        FailureCode.UNAVAILABLE,
        FailureCode.TIMEOUT,
    }
)


class _FrameEncodingError(ValueError):
    """Raised when an outbound unit cannot be represented safely within limits."""


def _reject_nan(constant: str) -> Any:
    raise ValueError(f"non-finite JSON constant is not allowed: {constant}")


def _extract_header(scope: Mapping[str, Any], name: bytes) -> str | None:
    target = name.lower()
    for key, value in scope.get("headers", ()):
        if (
            isinstance(key, bytes | bytearray)
            and bytes(key).lower() == target
            and isinstance(value, bytes | bytearray)
        ):
            return bytes(value).decode("latin-1")
    return None


def _decode_query_inputs(query_string: bytes | str) -> dict[str, Any] | None:
    raw = query_string.decode("latin-1") if isinstance(query_string, bytes) else query_string
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=False)
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            return None
        try:
            parsed = json.loads(value, parse_constant=_reject_nan)
        except ValueError:
            decoded[key] = value
        else:
            if isinstance(parsed, float) and not math.isfinite(parsed):
                return None
            decoded[key] = parsed
    return decoded


def _redact_failure(failure: Failure) -> dict[str, str]:
    if failure.code is FailureCode.INTERNAL_FAILURE:
        return dict(_REDACTED_ERROR)
    return {"code": failure.code.value, "message": failure.message}


def _close_code_for_failure(code: FailureCode) -> int:
    if code in _INTERNAL_CLOSE_CODES:
        return 1011
    return 1008


def _encode_json_frame(payload: Mapping[str, Any], max_frame_bytes: int) -> str:
    try:
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as error:
        raise _FrameEncodingError("stream frame is not valid finite UTF-8 JSON") from error
    if len(encoded.encode("utf-8")) > max_frame_bytes:
        raise _FrameEncodingError("encoded frame exceeds max_frame_bytes")
    return encoded


def _encode_unit_frame(unit: object, max_frame_bytes: int) -> str:
    try:
        json_value = serialize_json(unit)
    except (TypeError, ValueError, RecursionError) as error:
        raise _FrameEncodingError("stream unit cannot be serialized") from error
    return _encode_json_frame({"type": "unit", "data": json_value}, max_frame_bytes)


class _DisconnectWatcher:
    """Cancel only the consumer task if the peer sends ``websocket.disconnect``."""

    __slots__ = ("_consumer", "_receive", "_task", "seen")

    def __init__(self, receive: _Receive, consumer: asyncio.Task[Any]) -> None:
        self._receive = receive
        self._consumer = consumer
        self._task: asyncio.Task[None] | None = None
        self.seen = False

    async def __aenter__(self) -> _DisconnectWatcher:
        self._task = asyncio.create_task(self._watch())
        return self

    async def _watch(self) -> None:
        while True:
            message = await self._receive()
            if isinstance(message, Mapping) and message.get("type") == "websocket.disconnect":
                self.seen = True
                self._consumer.cancel()
                return

    async def __aexit__(self, *_: object) -> bool:
        task = self._task
        self._task = None
        if task is None:
            return False
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            if self._consumer.cancelling():
                raise
        return False


@dataclass(frozen=True, slots=True)
class WebSocketStreamProjection:
    """Bounded ASGI 3.0 WebSocket projector for one streaming ``ExecutionPlan``."""

    plan: ExecutionPlan
    container: DIContainer
    allowed_origins: frozenset[str]
    principals: Callable[[_Scope], Principal]
    input_mode: Literal["handshake", "initial_frame"] = "initial_frame"
    max_frame_bytes: int = 65_536
    initial_frame_timeout: float = 2.0
    attempt_timeout: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.plan, ExecutionPlan) or not self.plan.streaming:
            raise ValueError(
                "WebSocketStreamProjection requires a compiled streaming ExecutionPlan"
            )
        if not isinstance(self.container, DIContainer):
            raise TypeError("container must be a DIContainer")
        if self.input_mode not in {"handshake", "initial_frame"}:
            raise ValueError(f"unsupported input_mode: {self.input_mode!r}")
        if isinstance(self.max_frame_bytes, bool) or self.max_frame_bytes <= 0:
            raise ValueError("max_frame_bytes must be a positive integer")
        if isinstance(self.initial_frame_timeout, bool) or self.initial_frame_timeout <= 0:
            raise ValueError("initial_frame_timeout must be positive")
        if self.attempt_timeout is not None and (
            isinstance(self.attempt_timeout, bool) or self.attempt_timeout <= 0
        ):
            raise ValueError("attempt_timeout must be positive when set")

    def _deadline(self) -> float | None:
        if self.attempt_timeout is None:
            return None
        return asyncio.get_running_loop().time() + self.attempt_timeout

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        if scope.get("type") != "websocket":
            raise RuntimeError(f"unsupported scope type: {scope.get('type')!r}")

        connect = await receive()
        if connect.get("type") != "websocket.connect":
            await self._close(send, 1002, "expected websocket.connect")
            return

        origin = _extract_header(scope, b"origin")
        if origin is None or origin not in self.allowed_origins:
            await self._close(send, 1008, "origin not allowed")
            return

        principal = self.principals(scope)
        if not isinstance(principal, Principal):
            await self._close(send, 1008, "invalid principal")
            return

        if self.input_mode == "handshake":
            await self._serve_handshake_mode(scope, receive, send, principal)
        else:
            await self._serve_initial_frame_mode(receive, send, principal)

    async def _close(self, send: _Send, code: int, reason: str = "") -> None:
        with contextlib.suppress(OSError):
            await send({"type": "websocket.close", "code": code, "reason": reason})

    async def _send_terminal(
        self,
        send: _Send,
        *,
        outcome: str,
        units: int,
        error: Mapping[str, str] | None = None,
    ) -> bool:
        body: dict[str, Any] = {"type": "terminal", "outcome": outcome, "units": units}
        if error is not None:
            body["error"] = dict(error)
        try:
            encoded = _encode_json_frame(body, self.max_frame_bytes)
        except _FrameEncodingError:
            compact: dict[str, Any] = {"type": "terminal", "outcome": outcome, "units": units}
            if error is not None:
                compact["error"] = {
                    "code": error["code"],
                    "message": "capability invocation failed",
                }
            encoded = json.dumps(
                compact,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        try:
            await send({"type": "websocket.send", "text": encoded})
        except OSError:
            return False
        return True

    async def _serve_handshake_mode(
        self,
        scope: _Scope,
        receive: _Receive,
        send: _Send,
        principal: Principal,
    ) -> None:
        inputs = _decode_query_inputs(scope.get("query_string", b""))
        if inputs is None:
            await self._close(send, 1008, "invalid query parameters")
            return

        context = ExecutionContext(
            Invocation(self.plan.definition.id, inputs, {}, deadline=self._deadline()),
            self.container,
            principal=principal,
        )
        stream = open_stream(self.plan, context, input_materializer=materialize_json)
        async with contextlib.AsyncExitStack() as stack:
            try:
                await stack.enter_async_context(stream)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                failure = classify_failure(error, self.plan.definition.id)
                await self._close(send, _close_code_for_failure(failure.code), failure.code.value)
                return

            first_frame: str | None = None
            try:
                first_unit = await anext(stream)
            except StopAsyncIteration:
                pass
            except StreamInterrupted as interrupted:
                await self._close(
                    send,
                    _close_code_for_failure(interrupted.failure.code),
                    interrupted.failure.code.value,
                )
                return
            else:
                try:
                    first_frame = _encode_unit_frame(first_unit, self.max_frame_bytes)
                except _FrameEncodingError:
                    await self._close(send, 1011, "unrepresentable unit")
                    return

            try:
                await send({"type": "websocket.accept"})
            except OSError:
                return

            units = 0
            if first_frame is None:
                if await self._send_terminal(send, outcome=StreamTerminal.COMPLETED.value, units=0):
                    await self._close(send, 1000)
                return

            try:
                await send({"type": "websocket.send", "text": first_frame})
            except OSError:
                return
            units = 1
            await self._pump_after_accept(stream, receive, send, initial_units=units)

    async def _serve_initial_frame_mode(
        self,
        receive: _Receive,
        send: _Send,
        principal: Principal,
    ) -> None:
        try:
            await send({"type": "websocket.accept"})
        except OSError:
            return

        try:
            async with asyncio.timeout(self.initial_frame_timeout):
                message = await receive()
        except TimeoutError:
            await self._close(send, 1008, "initial frame timeout")
            return

        if message.get("type") == "websocket.disconnect":
            return

        raw_text = message.get("text")
        if message.get("type") != "websocket.receive" or not isinstance(raw_text, str):
            await self._send_terminal(
                send,
                outcome="failed",
                units=0,
                error={"code": FailureCode.INVALID_INPUT.value, "message": "expected text frame"},
            )
            await self._close(send, 1008, FailureCode.INVALID_INPUT.value)
            return

        if len(raw_text.encode("utf-8")) > self.max_frame_bytes:
            await self._close(send, 1009, "initial frame exceeds max_frame_bytes")
            return

        try:
            inputs = json.loads(raw_text, parse_constant=_reject_nan)
        except ValueError:
            await self._send_terminal(
                send,
                outcome="failed",
                units=0,
                error={"code": FailureCode.INVALID_INPUT.value, "message": "malformed JSON frame"},
            )
            await self._close(send, 1008, FailureCode.INVALID_INPUT.value)
            return

        if not isinstance(inputs, dict):
            await self._send_terminal(
                send,
                outcome="failed",
                units=0,
                error={
                    "code": FailureCode.INVALID_INPUT.value,
                    "message": "initial frame must be a JSON object",
                },
            )
            await self._close(send, 1008, FailureCode.INVALID_INPUT.value)
            return

        context = ExecutionContext(
            Invocation(self.plan.definition.id, inputs, {}, deadline=self._deadline()),
            self.container,
            principal=principal,
        )
        stream = open_stream(self.plan, context, input_materializer=materialize_json)
        async with contextlib.AsyncExitStack() as stack:
            try:
                await stack.enter_async_context(stream)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                failure = classify_failure(error, self.plan.definition.id)
                await self._send_terminal(
                    send,
                    outcome="failed",
                    units=0,
                    error=_redact_failure(failure),
                )
                await self._close(send, _close_code_for_failure(failure.code), failure.code.value)
                return

            await self._pump_after_accept(stream, receive, send, initial_units=0)

    async def _pump_after_accept(
        self,
        stream: CapabilityStream,
        receive: _Receive,
        send: _Send,
        *,
        initial_units: int,
    ) -> None:
        consumer = asyncio.current_task()
        assert consumer is not None
        watcher = _DisconnectWatcher(receive, consumer)
        units = initial_units
        try:
            async with watcher:
                while True:
                    try:
                        unit = await anext(stream)
                    except StopAsyncIteration:
                        if await self._send_terminal(
                            send,
                            outcome=StreamTerminal.COMPLETED.value,
                            units=units,
                        ):
                            await self._close(send, 1000)
                        return
                    except StreamInterrupted as interrupted:
                        failure = interrupted.failure
                        outcome = (
                            "failed"
                            if units == 0
                            else (stream.terminal or StreamTerminal.INTERRUPTED).value
                        )
                        if await self._send_terminal(
                            send,
                            outcome=outcome,
                            units=units,
                            error=_redact_failure(failure),
                        ):
                            await self._close(
                                send, _close_code_for_failure(failure.code), failure.code.value
                            )
                        return

                    try:
                        frame = _encode_unit_frame(unit, self.max_frame_bytes)
                    except _FrameEncodingError:
                        outcome = "failed" if units == 0 else StreamTerminal.INTERRUPTED.value
                        if await self._send_terminal(
                            send,
                            outcome=outcome,
                            units=units,
                            error=_REDACTED_ERROR,
                        ):
                            await self._close(send, 1011, FailureCode.INTERNAL_FAILURE.value)
                        return

                    try:
                        await send({"type": "websocket.send", "text": frame})
                    except OSError:
                        return
                    units += 1
        except asyncio.CancelledError:
            if watcher.seen and consumer.uncancel() == 0:
                return
            raise
