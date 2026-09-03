"""ASGI lifespan bridge for one application lifecycle.

The lifecycle is a single async context manager factory. Startup enters it,
shutdown exits it, and the dispatcher owns nothing else: it does not compile,
does not hold application state, and does not decide what a resource is.

The lifecycle deliberately cannot hand a value back. Application state belongs
to dependency providers, which are transport-neutral; smuggling it through an
HTTP adapter's lifespan return value would make HTTP the owner of state that
every other transport also needs.
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from enum import Enum, auto
from typing import Any

type _Scope = dict[str, Any]
type _Message = dict[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]
type _Send = Callable[[_Message], Awaitable[None]]

#: Called once per lifespan cycle to produce the lifecycle context manager.
type _Lifecycle = Callable[[], AbstractAsyncContextManager[None]]

_STARTUP = "lifespan.startup"
_SHUTDOWN = "lifespan.shutdown"


class _LifespanProtocolError(RuntimeError):
    """The ASGI server violated the lifespan protocol, or it ran twice."""


class _LifespanState(Enum):
    IDLE = auto()
    RUNNING = auto()
    CLOSED = auto()


class _LifespanDispatcher:
    """Run exactly one ASGI lifespan cycle against one application lifecycle."""

    __slots__ = ("_lifecycle", "_state")

    def __init__(self, lifecycle: _Lifecycle) -> None:
        if not callable(lifecycle):
            raise TypeError(f"lifecycle must be callable, got {type(lifecycle).__name__}")
        self._lifecycle = lifecycle
        self._state = _LifespanState.IDLE

    @property
    def state(self) -> _LifespanState:
        return self._state

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        if scope.get("type") != "lifespan":
            raise _LifespanProtocolError(f"not a lifespan scope: {scope.get('type')!r}")
        if self._state is not _LifespanState.IDLE:
            raise _LifespanProtocolError("this lifespan dispatcher has already run")

        _expect(await receive(), _STARTUP)
        context = self._lifecycle()
        if not isinstance(context, AbstractAsyncContextManager):
            raise TypeError(
                f"lifecycle must return an async context manager, got {type(context).__name__}"
            )

        try:
            entered = await context.__aenter__()
        except asyncio.CancelledError:
            raise
        except BaseException:
            # The message reaches the server operator's log, never a client,
            # so the traceback belongs here rather than being redacted.
            self._state = _LifespanState.CLOSED
            await send({"type": "lifespan.startup.failed", "message": traceback.format_exc()})
            return

        if entered is not None:
            self._state = _LifespanState.CLOSED
            await _exit_quietly(context)
            raise TypeError(
                "lifecycle context must yield None; application state belongs "
                "to dependency providers"
            )

        self._state = _LifespanState.RUNNING
        await send({"type": "lifespan.startup.complete"})

        try:
            _expect(await receive(), _SHUTDOWN)
        except BaseException:
            self._state = _LifespanState.CLOSED
            await _exit_quietly(context)
            raise

        try:
            await context.__aexit__(None, None, None)
        except asyncio.CancelledError:
            self._state = _LifespanState.CLOSED
            raise
        except BaseException:
            self._state = _LifespanState.CLOSED
            await send({"type": "lifespan.shutdown.failed", "message": traceback.format_exc()})
            return

        self._state = _LifespanState.CLOSED
        await send({"type": "lifespan.shutdown.complete"})


def _expect(message: _Message, expected: str) -> None:
    if not isinstance(message, dict):
        raise _LifespanProtocolError(
            f"ASGI event must be a dictionary, got {type(message).__name__}"
        )
    event_type = message.get("type")
    if not isinstance(event_type, str):
        raise _LifespanProtocolError("ASGI event 'type' must be a string")
    if event_type != expected:
        raise _LifespanProtocolError(f"expected {expected!r}, got {event_type!r}")


async def _exit_quietly(context: AbstractAsyncContextManager[None]) -> None:
    """Release the lifecycle without masking the failure already in flight."""
    try:
        await context.__aexit__(None, None, None)
    except asyncio.CancelledError:
        raise
    except BaseException:
        return
