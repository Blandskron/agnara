"""ASGI lifespan bridge for the HTTP adapter (E6.6)."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest

from agnara_http._asgi import _ASGIBoundary, _UnsupportedScopeError
from agnara_http._lifespan import (
    _LifespanDispatcher,
    _LifespanProtocolError,
    _LifespanState,
)

type Message = dict[str, Any]

LIFESPAN_SCOPE: dict[str, Any] = {
    "type": "lifespan",
    "asgi": {"version": "3.0", "spec_version": "2.5"},
}


class Recorder:
    """A lifecycle that records what happened to it."""

    def __init__(
        self,
        *,
        fail_startup: bool = False,
        fail_shutdown: bool = False,
        cancel_startup: bool = False,
        cancel_shutdown: bool = False,
        yields: object = None,
    ) -> None:
        self.events: list[str] = []
        self.calls = 0
        self._fail_startup = fail_startup
        self._fail_shutdown = fail_shutdown
        self._cancel_startup = cancel_startup
        self._cancel_shutdown = cancel_shutdown
        self._yields = yields

    def __call__(self) -> Any:
        self.calls += 1

        @asynccontextmanager
        async def lifecycle() -> AsyncIterator[Any]:
            if self._cancel_startup:
                raise asyncio.CancelledError
            if self._fail_startup:
                raise RuntimeError("database pool unavailable")
            self.events.append("enter")
            try:
                yield self._yields
            finally:
                self.events.append("exit")
                if self._cancel_shutdown:
                    raise asyncio.CancelledError
                if self._fail_shutdown:
                    raise RuntimeError("connection drain timed out")

        return lifecycle()


def channels(events: list[str]) -> tuple[Callable[[], Awaitable[Message]], list[Message], Any]:
    """Build a receive that yields the given event types, and a send recorder."""
    pending = list(events)
    sent: list[Message] = []

    async def receive() -> Message:
        if not pending:
            raise AssertionError("the dispatcher asked for more events than the test supplied")
        return {"type": pending.pop(0)}

    async def send(message: Message) -> None:
        sent.append(message)

    return receive, sent, send


def run_cycle(
    recorder: Recorder,
    events: list[str],
) -> tuple[_LifespanDispatcher, list[Message]]:
    dispatcher = _LifespanDispatcher(recorder)
    receive, sent, send = channels(events)
    asyncio.run(dispatcher(LIFESPAN_SCOPE, receive, send))
    return dispatcher, sent


def test_a_complete_cycle_enters_and_exits_the_lifecycle_exactly_once() -> None:
    recorder = Recorder()
    dispatcher, sent = run_cycle(recorder, ["lifespan.startup", "lifespan.shutdown"])

    assert sent == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]
    assert recorder.events == ["enter", "exit"]
    assert recorder.calls == 1
    assert dispatcher.state is _LifespanState.CLOSED


def test_the_dispatcher_is_idle_until_the_server_starts_it() -> None:
    dispatcher = _LifespanDispatcher(Recorder())
    assert dispatcher.state is _LifespanState.IDLE


def test_startup_failure_reports_the_traceback_and_never_completes() -> None:
    recorder = Recorder(fail_startup=True)
    dispatcher, sent = run_cycle(recorder, ["lifespan.startup"])

    assert len(sent) == 1
    assert sent[0]["type"] == "lifespan.startup.failed"
    assert "database pool unavailable" in sent[0]["message"]
    assert "RuntimeError" in sent[0]["message"]
    assert recorder.events == []
    assert dispatcher.state is _LifespanState.CLOSED


def test_startup_failure_does_not_ask_for_a_shutdown_event() -> None:
    # channels() raises if the dispatcher reads more events than supplied, so
    # a single supplied event proves shutdown was never requested.
    recorder = Recorder(fail_startup=True)
    _, sent = run_cycle(recorder, ["lifespan.startup"])
    assert [message["type"] for message in sent] == ["lifespan.startup.failed"]


def test_shutdown_failure_reports_the_traceback_after_a_successful_startup() -> None:
    recorder = Recorder(fail_shutdown=True)
    dispatcher, sent = run_cycle(recorder, ["lifespan.startup", "lifespan.shutdown"])

    assert sent[0] == {"type": "lifespan.startup.complete"}
    assert sent[1]["type"] == "lifespan.shutdown.failed"
    assert "connection drain timed out" in sent[1]["message"]
    assert recorder.events == ["enter", "exit"]
    assert dispatcher.state is _LifespanState.CLOSED


def test_cancellation_during_startup_propagates_instead_of_failing_the_lifespan() -> None:
    recorder = Recorder(cancel_startup=True)
    dispatcher = _LifespanDispatcher(recorder)
    receive, sent, send = channels(["lifespan.startup"])

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(dispatcher(LIFESPAN_SCOPE, receive, send))

    assert sent == []


def test_cancellation_during_shutdown_propagates_instead_of_failing_the_lifespan() -> None:
    recorder = Recorder(cancel_shutdown=True)
    dispatcher = _LifespanDispatcher(recorder)
    receive, sent, send = channels(["lifespan.startup", "lifespan.shutdown"])

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(dispatcher(LIFESPAN_SCOPE, receive, send))

    assert sent == [{"type": "lifespan.startup.complete"}]
    assert dispatcher.state is _LifespanState.CLOSED


def test_an_unexpected_first_event_is_refused_before_the_lifecycle_is_built() -> None:
    recorder = Recorder()
    dispatcher = _LifespanDispatcher(recorder)
    receive, sent, send = channels(["lifespan.shutdown"])

    with pytest.raises(_LifespanProtocolError, match=r"expected 'lifespan\.startup'"):
        asyncio.run(dispatcher(LIFESPAN_SCOPE, receive, send))

    assert recorder.calls == 0
    assert sent == []


def test_an_unexpected_second_event_releases_the_lifecycle() -> None:
    recorder = Recorder()
    dispatcher = _LifespanDispatcher(recorder)
    receive, sent, send = channels(["lifespan.startup", "lifespan.startup"])

    with pytest.raises(_LifespanProtocolError, match=r"expected 'lifespan\.shutdown'"):
        asyncio.run(dispatcher(LIFESPAN_SCOPE, receive, send))

    assert recorder.events == ["enter", "exit"]
    assert sent == [{"type": "lifespan.startup.complete"}]
    assert dispatcher.state is _LifespanState.CLOSED


@pytest.mark.parametrize(
    ("event", "message"),
    [
        (object(), "ASGI event must be a dictionary, got object"),
        ({}, "ASGI event 'type' must be a string"),
        ({"type": 42}, "ASGI event 'type' must be a string"),
    ],
)
def test_a_malformed_event_is_refused(event: object, message: str) -> None:
    dispatcher = _LifespanDispatcher(Recorder())
    sent: list[Message] = []

    async def receive() -> Any:
        return event

    async def send(item: Message) -> None:
        sent.append(item)

    with pytest.raises(_LifespanProtocolError, match=message):
        asyncio.run(dispatcher(LIFESPAN_SCOPE, receive, send))

    assert sent == []


def test_a_second_cycle_on_the_same_dispatcher_is_refused() -> None:
    recorder = Recorder()
    dispatcher, _ = run_cycle(recorder, ["lifespan.startup", "lifespan.shutdown"])
    receive, sent, send = channels(["lifespan.startup", "lifespan.shutdown"])

    with pytest.raises(_LifespanProtocolError, match="already run"):
        asyncio.run(dispatcher(LIFESPAN_SCOPE, receive, send))

    assert recorder.calls == 1
    assert sent == []


def test_a_non_lifespan_scope_is_refused() -> None:
    dispatcher = _LifespanDispatcher(Recorder())
    receive, _, send = channels([])

    with pytest.raises(_LifespanProtocolError, match="not a lifespan scope: 'http'"):
        asyncio.run(dispatcher({"type": "http"}, receive, send))


def test_a_non_callable_lifecycle_is_refused() -> None:
    with pytest.raises(TypeError, match="lifecycle must be callable, got object"):
        _LifespanDispatcher(object())  # ty: ignore[invalid-argument-type]


def test_a_lifecycle_that_is_not_an_async_context_manager_is_refused() -> None:
    dispatcher = _LifespanDispatcher(lambda: object())  # ty: ignore[invalid-argument-type]
    receive, _, send = channels(["lifespan.startup"])

    with pytest.raises(TypeError, match="must return an async context manager, got object"):
        asyncio.run(dispatcher(LIFESPAN_SCOPE, receive, send))


def test_a_lifecycle_that_yields_a_value_is_refused_and_released() -> None:
    # Application state belongs to dependency providers. Accepting it here
    # would make the HTTP adapter the owner of transport-neutral state.
    recorder = Recorder(yields={"pool": "handle"})
    dispatcher = _LifespanDispatcher(recorder)
    receive, sent, send = channels(["lifespan.startup"])

    with pytest.raises(TypeError, match="must yield None"):
        asyncio.run(dispatcher(LIFESPAN_SCOPE, receive, send))

    assert recorder.events == ["enter", "exit"]
    assert sent == []
    assert dispatcher.state is _LifespanState.CLOSED


def test_the_boundary_routes_a_lifespan_scope_to_the_configured_dispatcher() -> None:
    async def run_test() -> None:
        recorder = Recorder()
        dispatcher = _LifespanDispatcher(recorder)
        receive, sent, send = channels(["lifespan.startup", "lifespan.shutdown"])
        http_calls = 0

        async def http_dispatch(scope: Any, receive_: Any, send_: Any) -> None:
            nonlocal http_calls
            del scope, receive_, send_
            http_calls += 1

        boundary = _ASGIBoundary(http_dispatch, dispatcher)
        await boundary(LIFESPAN_SCOPE, receive, send)

        assert [message["type"] for message in sent] == [
            "lifespan.startup.complete",
            "lifespan.shutdown.complete",
        ]
        assert http_calls == 0

    asyncio.run(run_test())


def test_the_boundary_still_refuses_lifespan_without_a_dispatcher() -> None:
    async def run_test() -> None:
        async def http_dispatch(scope: Any, receive_: Any, send_: Any) -> None:
            del scope, receive_, send_

        receive, _, send = channels([])
        with pytest.raises(_UnsupportedScopeError, match="unsupported ASGI scope type: 'lifespan'"):
            await _ASGIBoundary(http_dispatch)(LIFESPAN_SCOPE, receive, send)

    asyncio.run(run_test())


def test_the_boundary_refuses_websocket_whether_or_not_lifespan_is_configured() -> None:
    async def run_test() -> None:
        async def http_dispatch(scope: Any, receive_: Any, send_: Any) -> None:
            del scope, receive_, send_

        receive, _, send = channels([])
        for lifespan in (None, _LifespanDispatcher(Recorder())):
            with pytest.raises(
                _UnsupportedScopeError, match="unsupported ASGI scope type: 'websocket'"
            ):
                await _ASGIBoundary(http_dispatch, lifespan)({"type": "websocket"}, receive, send)

    asyncio.run(run_test())


def test_the_boundary_refuses_a_non_callable_lifespan_dispatcher() -> None:
    async def http_dispatch(scope: Any, receive_: Any, send_: Any) -> None:
        del scope, receive_, send_

    with pytest.raises(TypeError, match="lifespan must be callable, got object"):
        _ASGIBoundary(http_dispatch, object())  # ty: ignore[invalid-argument-type]
