"""Application-owned opt-in disconnect recipe for a dedicated A2A surface.

Copy this stdlib-only companion module into the application's host boundary.
It is not an Agnara export or a standalone server. See docs/A2A_SERVICE.md.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine, MutableMapping
from typing import Any

type _Message = MutableMapping[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]
type _Send = Callable[[_Message], Awaitable[None]]
type _ASGI = Callable[[_Message, _Receive, _Send], Awaitable[None]]
type _WrappedASGI = Callable[[_Message, _Receive, _Send], Coroutine[Any, Any, None]]


def cancel_on_disconnect(application: _ASGI) -> _WrappedASGI:
    """Opt in to cancelling a pending POST task on EOF, then join its cleanup.

    One pump owns the underlying receive stream. It starts only when the
    application first asks for input, preserving a no-read authentication
    refusal. A capacity permit bounds queued/in-flight input to one event.
    All mutable state belongs to this request on its owning event loop.
    """

    async def wrapped(scope: _Message, receive: _Receive, send: _Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await application(scope, receive, send)
            return

        owner = asyncio.current_task()
        assert owner is not None
        demand = asyncio.Event()
        capacity = asyncio.Semaphore(1)
        incoming: asyncio.Queue[_Message] = asyncio.Queue(maxsize=1)
        response_complete = False

        async def pump() -> None:
            await demand.wait()
            while True:
                await capacity.acquire()
                message = await receive()
                incoming.put_nowait(message)
                if message["type"] == "http.disconnect":
                    return

        async def application_receive() -> _Message:
            demand.set()
            message = await incoming.get()
            capacity.release()
            return message

        async def application_send(message: _Message) -> None:
            nonlocal response_complete
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                response_complete = True

        async def dispatch() -> None:
            await application(scope, application_receive, application_send)

        async with asyncio.TaskGroup() as owned:
            request = owned.create_task(dispatch())
            receiver = owned.create_task(pump())
            cancelled_for_disconnect = False
            try:
                completed, _ = await asyncio.wait(
                    (request, receiver), return_when=asyncio.FIRST_COMPLETED
                )
                if (
                    receiver in completed
                    and not request.done()
                    and not request.cancelling()
                    and not response_complete
                ):
                    cancelled_for_disconnect = request.cancel("peer disconnected")
                try:
                    await request
                except asyncio.CancelledError:
                    # Suppress only this policy's own cancellation of the
                    # disconnected request. External cancellation still exits
                    # the host; TaskGroup preserves non-cancellation errors.
                    if not cancelled_for_disconnect or owner.cancelling():
                        raise
            finally:
                receiver.cancel()

    return wrapped
