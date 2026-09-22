"""One FastAPI process with native and public Agnara HTTP routes side by side."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from agnara import Agnara, App
from agnara_http import Binding, BindingSource, Http


@dataclass
class State:
    starts: int = 0
    stops: int = 0


def build_host(state: State) -> FastAPI:
    project = Agnara("dogfood_side_by_side")
    app = App("status")

    @app.capability
    def check(value: str) -> dict[str, str]:
        return {"agnara": value}

    project.include(app)
    capabilities = project.compile()
    surface = Http("dogfood")
    surface.get("/check/{value}", check, Binding("value", BindingSource.PATH))
    agnara_http = surface.compile(capabilities)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state.starts += 1
        try:
            yield
        finally:
            state.stops += 1

    host = FastAPI(lifespan=lifespan)

    @host.get("/native")
    async def native() -> dict[str, str]:
        return {"native": "fastapi"}

    async def mounted(
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None:
        await agnara_http(dict(scope), receive, send)

    host.mount("/agnara", mounted)
    return host


async def request(host: FastAPI, path: str) -> tuple[int, dict[str, object]]:
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> MutableMapping[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(dict(message))

    await host(
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
            "headers": [],
            "client": ("127.0.0.1", 9001),
            "server": ("test", 80),
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent)
    return int(start["status"]), json.loads(body)


async def main() -> None:
    state = State()
    host = build_host(state)
    async with host.router.lifespan_context(host):
        assert await request(host, "/native") == (200, {"native": "fastapi"})
        assert await request(host, "/agnara/check/ready") == (200, {"agnara": "ready"})
    assert (state.starts, state.stops) == (1, 1)
    print("SIDE_BY_SIDE_DOGFOOD_OK")


if __name__ == "__main__":
    asyncio.run(main())
