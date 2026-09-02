import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from agnara_http._asgi import _ASGIBoundary, _UnsupportedScopeError

type Message = dict[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]


def http_scope() -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.5"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/health",
        "raw_path": b"/health",
        "query_string": b"",
        "root_path": "",
        "headers": [],
    }


def io_callables() -> tuple[Receive, Send]:
    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        del message

    return receive, send


def test_delegates_http_scope_once_without_copying_asgi_objects() -> None:
    async def run_test() -> None:
        scope = http_scope()
        receive, send = io_callables()
        calls: list[tuple[object, object, object]] = []

        async def dispatch(
            dispatched_scope: dict[str, Any],
            dispatched_receive: Receive,
            dispatched_send: Send,
        ) -> None:
            calls.append((dispatched_scope, dispatched_receive, dispatched_send))

        boundary = _ASGIBoundary(dispatch)

        assert await boundary(scope, receive, send) is None
        assert calls == [(scope, receive, send)]
        assert calls[0][0] is scope
        assert calls[0][1] is receive
        assert calls[0][2] is send

    asyncio.run(run_test())


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket", "agnara.test"])
def test_rejects_unsupported_scope_before_dispatch(scope_type: str) -> None:
    async def run_test() -> None:
        dispatched = False

        async def dispatch(scope: dict[str, Any], receive: Receive, send: Send) -> None:
            nonlocal dispatched
            del scope, receive, send
            dispatched = True

        receive, send = io_callables()
        boundary = _ASGIBoundary(dispatch)

        with pytest.raises(
            _UnsupportedScopeError,
            match=rf"unsupported ASGI scope type: '{scope_type}'",
        ):
            await boundary({"type": scope_type}, receive, send)

        assert not dispatched

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("scope", "message"),
    [
        (object(), "ASGI scope must be a dictionary, got object"),
        ({}, "ASGI scope 'type' must be a string"),
        ({"type": 42}, "ASGI scope 'type' must be a string"),
    ],
)
def test_rejects_malformed_scope(scope: object, message: str) -> None:
    async def run_test() -> None:
        async def dispatch(scope: dict[str, Any], receive: Receive, send: Send) -> None:
            del scope, receive, send

        receive, send = io_callables()
        boundary = _ASGIBoundary(dispatch)

        with pytest.raises(TypeError, match=message):
            await boundary(scope, receive, send)  # type: ignore

    asyncio.run(run_test())


def test_rejects_non_callable_dispatcher() -> None:
    with pytest.raises(TypeError, match="dispatch must be callable, got object"):
        _ASGIBoundary(object())  # type: ignore


@pytest.mark.parametrize(
    ("invalid_name", "message"),
    [
        ("receive", "ASGI receive must be callable, got object"),
        ("send", "ASGI send must be callable, got object"),
    ],
)
def test_rejects_non_callable_channel(
    invalid_name: str,
    message: str,
) -> None:
    async def run_test() -> None:
        dispatched = False

        async def dispatch(scope: dict[str, Any], receive: Receive, send: Send) -> None:
            nonlocal dispatched
            del scope, receive, send
            dispatched = True

        receive, send = io_callables()
        boundary = _ASGIBoundary(dispatch)
        boundary_call: Any = boundary
        receive_value: Any = receive
        send_value: Any = send
        if invalid_name == "receive":
            receive_value = object()
        else:
            send_value = object()

        with pytest.raises(TypeError, match=message):
            await boundary_call(http_scope(), receive_value, send_value)

        assert not dispatched

    asyncio.run(run_test())


def test_propagates_dispatcher_exception_without_wrapping() -> None:
    async def run_test() -> None:
        class DispatchError(RuntimeError):
            pass

        expected = DispatchError("dispatch failed")

        async def dispatch(scope: dict[str, Any], receive: Receive, send: Send) -> None:
            del scope, receive, send
            raise expected

        receive, send = io_callables()

        with pytest.raises(DispatchError) as raised:
            await _ASGIBoundary(dispatch)(http_scope(), receive, send)

        assert raised.value is expected

    asyncio.run(run_test())


def test_propagates_dispatcher_cancellation() -> None:
    async def run_test() -> None:
        async def dispatch(scope: dict[str, Any], receive: Receive, send: Send) -> None:
            del scope, receive, send
            raise asyncio.CancelledError

        receive, send = io_callables()

        with pytest.raises(asyncio.CancelledError):
            await _ASGIBoundary(dispatch)(http_scope(), receive, send)

    asyncio.run(run_test())
