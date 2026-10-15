"""One FastAPI process with native and public Agnara HTTP routes side by side."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, MutableMapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI

from agnara import Agnara, App
from agnara.di import DIRegistry, Scope, provider
from agnara_http import Binding, BindingSource, Http, HttpApplication


@dataclass
class Resource:
    closed: bool = False

    async def read(self, value: str) -> str:
        assert not self.closed
        return value


@dataclass
class State:
    starts: int = 0
    stops: int = 0
    child: HttpApplication | None = None
    resources: list[Resource] = field(default_factory=list)
    events: list[tuple[str, int]] = field(default_factory=list)

    def record(self, event: str) -> None:
        self.events.append((event, id(asyncio.get_running_loop())))


@asynccontextmanager
async def child_lifespan(application: Any, *, timeout: float = 5) -> AsyncIterator[None]:
    """Fixture-owned ASGI handshake; mounts do not start their child lifespans."""
    incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    async with asyncio.TaskGroup() as tasks:
        task = tasks.create_task(
            application(
                {"type": "lifespan", "asgi": {"version": "3.0", "spec_version": "2.0"}},
                incoming.get,
                outgoing.put,
            )
        )
        async with asyncio.timeout(timeout):
            await incoming.put({"type": "lifespan.startup"})
            message = await outgoing.get()
        if message["type"] != "lifespan.startup.complete":
            raise RuntimeError("child startup failed")
        try:
            yield
        finally:
            # The caller must drain HTTP work before leaving this context.
            async with asyncio.timeout(timeout):
                await incoming.put({"type": "lifespan.shutdown"})
                message = await outgoing.get()
                if message["type"] != "lifespan.shutdown.complete":
                    raise RuntimeError("child shutdown failed")
                await task


def compile_child(state: State) -> HttpApplication:
    project = Agnara("dogfood_side_by_side")
    app = App("status")

    @app.capability(output=dict[str, str])
    async def check(value: str, resource: Resource) -> dict[str, str]:
        state.record("invoke")
        return {"agnara": await resource.read(value)}

    project.include(app)
    capabilities = project.compile()
    dependencies = DIRegistry()

    @provider(scope=Scope.SINGLETON)
    async def resource() -> AsyncIterator[Resource]:
        item = Resource()
        state.resources.append(item)
        state.record("resource.open")
        try:
            yield item
        finally:
            item.closed = True
            state.record("resource.close")

    dependencies.bind(Resource, resource)

    @asynccontextmanager
    async def lifecycle() -> AsyncIterator[None]:
        state.record("child.start")
        try:
            yield
        finally:
            state.record("child.stop")

    surface = Http("dogfood")
    surface.get("/check/{value}", check, Binding("value", BindingSource.PATH))
    child = surface.compile(capabilities, dependencies=dependencies, lifecycle=lifecycle)
    state.record("child.compile")
    return child


def build_host(state: State) -> FastAPI:

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state.starts += 1
        state.record("host.start")
        try:
            state.child = compile_child(state)
            async with child_lifespan(state.child):
                yield
        finally:
            state.child = None
            state.stops += 1
            state.record("host.stop")

    host = FastAPI(lifespan=lifespan)

    @host.get("/native")
    async def native() -> dict[str, str]:
        return {"native": "fastapi"}

    async def mounted(
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None:
        assert state.child is not None
        await state.child(dict(scope), receive, send)

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
    before = asyncio.all_tasks()
    for exceptional in (False, True):
        state = State()
        host = build_host(state)
        raised = False
        try:
            async with host.router.lifespan_context(host):
                assert await request(host, "/native") == (200, {"native": "fastapi"})
                assert state.resources == []
                for value in ("ready", "again"):
                    assert await request(host, f"/agnara/check/{value}") == (200, {"agnara": value})
                assert len(state.resources) == 1 and not state.resources[0].closed
                if exceptional:
                    raise RuntimeError("host exit")
        except* RuntimeError as errors:
            assert exceptional and len(errors.exceptions) == 1
            assert str(errors.exceptions[0]) == "host exit"
            raised = True
        assert raised is exceptional
        assert (state.starts, state.stops) == (1, 1)
        assert state.child is None and state.resources[0].closed
        assert [name for name, _ in state.events] == [
            "host.start",
            "child.compile",
            "child.start",
            "resource.open",
            "invoke",
            "invoke",
            "resource.close",
            "child.stop",
            "host.stop",
        ]
        assert len({loop for _, loop in state.events}) == 1
        assert asyncio.all_tasks() == before
    print("SIDE_BY_SIDE_DOGFOOD_OK")


if __name__ == "__main__":
    asyncio.run(main())
