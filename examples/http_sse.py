"""Server-free HTTP SSE lifecycle demonstration using governed public APIs.

Run with ``uv run python examples/http_sse.py``. See docs/HTTP_SSE.md.
The ASGI peer below is an in-memory demonstration, not a network client.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from agnara import Agnara
from agnara.di import DIRegistry, Scope, provider
from agnara_http import Binding, BindingSource, Http


class ReportSession:
    """A local stand-in for an invocation-owned report resource."""


async def run_case(mode: str, *, count: str = "2") -> dict[str, Any]:
    """Compile a fresh surface and own one lifespan and HTTP connection."""
    lifecycle: list[str] = []

    @provider(scope=Scope.INVOCATION)
    async def provide_session() -> AsyncIterator[ReportSession]:
        lifecycle.append("provider.open")
        try:
            yield ReportSession()
        finally:
            lifecycle.append("provider.close")

    app = Agnara("reports")

    @app.capability(streaming=True, output=dict[str, int])
    async def rows(count: int, session: ReportSession) -> AsyncIterator[dict[str, int]]:
        # The resource is injected by type; no request object enters this handler.
        lifecycle.append("producer.open")
        try:
            if mode == "first_failure":
                raise RuntimeError("demo-private-diagnostic")
            for line in range(count):
                lifecycle.append(f"produce:{line}")
                yield {"line": line}
                if mode == "late_failure":
                    raise RuntimeError("demo-private-diagnostic")
                if mode == "disconnect":
                    # The peer disconnects after the first send. Its cancellation
                    # reaches this wait, so there is no timing sleep or prefetch.
                    await asyncio.Event().wait()
        finally:
            lifecycle.append("producer.close")

    @app.capability(streaming=True, output=dict[str, int], scopes=("reports:read",))
    async def protected(session: ReportSession) -> AsyncIterator[dict[str, int]]:
        lifecycle.append("protected.handler")
        yield {"line": 999}

    dependencies = DIRegistry()
    dependencies.bind(ReportSession, provide_session)
    http = Http("public")
    http.sse("/rows", rows, Binding("count", BindingSource.QUERY), max_event_bytes=1024)
    http.sse("/protected", protected)
    asgi = http.compile(app.compile(), dependencies=dependencies, request_timeout=2)

    incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    incoming.put_nowait({"type": "http.request", "body": b"", "more_body": False})
    events: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        events.append(message)
        if mode == "disconnect" and message.get("body", b"").startswith(b"data: "):
            incoming.put_nowait({"type": "http.disconnect"})

    lifespan_in: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    lifespan_out: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    path = "/protected" if mode == "denied" else "/rows"
    # The task group joins lifespan on every exit, including failure/cancellation.
    async with asyncio.timeout(5), asyncio.TaskGroup() as owned:
        owned.create_task(asgi({"type": "lifespan"}, lifespan_in.get, lifespan_out.put))
        await lifespan_in.put({"type": "lifespan.startup"})
        startup = await lifespan_out.get()
        if startup["type"] != "lifespan.startup.complete":
            raise RuntimeError("example lifespan startup failed")
        try:
            await asgi(
                {
                    "type": "http",
                    "method": "GET",
                    "path": path,
                    "raw_path": path.encode("ascii"),
                    "query_string": f"count={count}".encode("ascii"),
                    "headers": [],
                    "root_path": "",
                },
                incoming.get,
                send,
            )
        finally:
            await lifespan_in.put({"type": "lifespan.shutdown"})
            shutdown = await lifespan_out.get()
            if shutdown["type"] != "lifespan.shutdown.complete":
                raise RuntimeError("example lifespan shutdown failed")

    body = b"".join(event.get("body", b"") for event in events[1:])
    headers = dict(events[0]["headers"])
    units: list[dict[str, int]] = []
    terminal: dict[str, Any] | None = None
    problem: dict[str, Any] | None = None
    if events[0]["status"] == 200:
        # This bounded fixture receives complete adapter frames. A network
        # client must parse SSE incrementally across arbitrary byte chunks.
        for frame in body.decode("utf-8").split("\n\n"):
            if frame.startswith("event: agnara.terminal\ndata: "):
                terminal = json.loads(frame.split("\ndata: ", 1)[1])
            elif frame.startswith("data: "):
                units.append(json.loads(frame.removeprefix("data: ")))
    else:
        problem = json.loads(body)
    return {
        "status": events[0]["status"],
        "headers": headers,
        "units": units,
        "terminal": terminal,
        "problem": problem,
        "body": body,
        "lifecycle": lifecycle,
    }


async def demonstrate() -> dict[str, dict[str, Any]]:
    outcomes = {}
    for mode in (
        "completed",
        "denied",
        "invalid_input",
        "first_failure",
        "late_failure",
        "disconnect",
    ):
        outcomes[mode] = await run_case(mode, count="bad" if mode == "invalid_input" else "2")
    return outcomes


def main() -> None:
    for name, result in asyncio.run(demonstrate()).items():
        terminal = result["terminal"]
        problem = result["problem"]
        outcome = (
            terminal["outcome"] if terminal else problem["code"] if problem else "disconnected"
        )
        closed = result["lifecycle"].count("provider.close")
        print(
            f"{name}: status={result['status']} units={len(result['units'])} "
            f"outcome={outcome} closed={closed}"
        )


if __name__ == "__main__":
    main()
