"""Real loopback TCP evidence for one pinned host, not universal ASGI support.

Uvicorn/h11 does not cancel application work on peer disconnect. These tests
separate that observation from kernel deadline cancellation and host shutdown.
"""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import Any

import httpx
import uvicorn
from a2a.client.transports.jsonrpc import JsonRpcTransport
from a2a.types import a2a_pb2
from google.protobuf import json_format

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import ExecutionContext, ExecutionPlan
from agnara_a2a import A2a, A2aAgentCard, build_a2a_app

HEADERS = {"Authorization": "Bearer fixture-reader", "A2A-Version": "1.0"}


class Pool:
    closed = False


class Ledger:
    closed = False


@dataclass
class Observation:
    effects: list[str] = field(default_factory=list)
    lifecycle: list[str] = field(default_factory=list)
    loops: set[int] = field(default_factory=set)
    pools: list[Pool] = field(default_factory=list)
    ledgers: list[Ledger] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    principals: list[str | None] = field(default_factory=list)
    metadata: list[dict[str, Any]] = field(default_factory=list)
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    body_received: asyncio.Event = field(default_factory=asyncio.Event)
    request_closed: asyncio.Event = field(default_factory=asyncio.Event)
    disconnect_received: asyncio.Event = field(default_factory=asyncio.Event)
    active: int = 0

    def record(self, event: str) -> None:
        self.loops.add(id(asyncio.get_running_loop()))
        self.effects.append(event)


def compose(url: str, state: Observation, timeout: float):
    app = Agnara("network")

    @provider(scope=Scope.SINGLETON)
    async def pool() -> AsyncIterator[Pool]:
        resource = Pool()
        state.pools.append(resource)
        state.record("pool.open")
        try:
            yield resource
        finally:
            resource.closed = True
            state.record("pool.close")

    @provider()
    async def ledger(pool: Pool) -> AsyncIterator[Ledger]:
        resource = Ledger()
        state.ledgers.append(resource)
        state.record("ledger.open")
        try:
            yield resource
        finally:
            resource.closed = True
            state.record("ledger.close")

    @app.capability(scopes=("network:read",), output=int)
    async def double(value: int, ledger: Ledger, context: ExecutionContext) -> int:
        state.principals.append(context.principal.identity)
        state.metadata.append(dict(context.invocation.metadata))
        state.record("handler.enter")
        state.entered.set()
        try:
            if value == -1:
                await asyncio.Event().wait()
            elif value == -2:
                await state.release.wait()
            return value * 2
        except asyncio.CancelledError:
            state.record("handler.cancel")
            raise
        finally:
            state.record("handler.close")

    dependencies = DIRegistry()
    dependencies.bind(Pool, pool)
    dependencies.bind(Ledger, ledger)
    a2a = A2a(app)
    a2a.skill(double, id="double", name="Double", description="Doubles an integer", tags=("test",))
    plans = [ExecutionPlan.compile(d, dependencies) for d in app.compile().values()]
    container = DIContainer(dependencies)
    application = build_a2a_app(
        a2a.compile(),
        plans,
        container,
        card=A2aAgentCard(name="Network fixture", description="Loopback only", version="test"),
        url=url,
        principals=lambda scope: scope.get("fixture.principal"),
        challenge='Bearer realm="loopback"',
        timeout=timeout,
    )
    return application, container


class TestServer(uvicorn.Server):
    __test__ = False

    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        # Tests own this task, not process signal handlers.
        yield


@asynccontextmanager
async def serve(*, timeout: float = 0.5, wrap=None):
    """Own listener, server task and lifespan/container on one event loop."""
    state = Observation()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.setblocking(False)
    address = listener.getsockname()
    url = f"http://127.0.0.1:{address[1]}/"
    application = None

    async def host(scope: Any, receive: Any, send: Any) -> None:
        nonlocal application
        if scope["type"] == "lifespan":
            assert (await receive())["type"] == "lifespan.startup"
            application, container = compose(url, state, timeout)
            if wrap is not None:
                application = wrap(application)
            state.lifecycle.append("lifespan.start")
            state.loops.add(id(asyncio.get_running_loop()))
            try:
                await send({"type": "lifespan.startup.complete"})
                assert (await receive())["type"] == "lifespan.shutdown"
                assert state.active == 0, "host closed lifespan before requests drained"
                state.lifecycle.append("requests.drained")
            finally:
                await container.aclose()
                state.lifecycle.append("container.close")
            await send({"type": "lifespan.shutdown.complete"})
            state.lifecycle.append("lifespan.close")
            return
        assert application is not None
        tokens = {
            b"Bearer fixture-reader": Principal("reader", scopes={"network:read"}),
            b"Bearer fixture-unscoped": Principal("unscoped"),
        }
        principal = tokens.get(dict(scope["headers"]).get(b"authorization"))
        body = bytearray()

        async def observed_receive():
            message = await receive()
            if message["type"] == "http.request" and message.get("body"):
                state.body_received.set()
            elif message["type"] == "http.disconnect":
                state.disconnect_received.set()
            return message

        async def observed_send(message):
            if message["type"] == "http.response.body":
                body.extend(message.get("body", b""))
            await send(message)

        state.active += 1
        try:
            await application(
                {**scope, "fixture.principal": principal}, observed_receive, observed_send
            )
        finally:
            if body:
                state.outcomes.append(json.loads(body))
            state.active -= 1
            state.lifecycle.append("request.close")
            state.request_closed.set()

    config = uvicorn.Config(
        host,
        host="127.0.0.1",
        port=address[1],
        http="h11",
        ws="none",
        lifespan="on",
        log_config=None,
        access_log=False,
        proxy_headers=False,
        timeout_graceful_shutdown=5,
    )
    server = TestServer(config)
    before = asyncio.all_tasks()
    try:
        async with asyncio.timeout(15), asyncio.TaskGroup() as owned:
            task = owned.create_task(server.serve(sockets=[listener]))
            while not server.started:
                if task.done():
                    await task
                    raise AssertionError("loopback server exited before startup")
                await asyncio.sleep(0.01)
            try:
                yield url, state, server
            finally:
                server.should_exit = True
        assert not server.server_state.tasks
        assert all(not s.is_serving() for s in server.servers)
        assert asyncio.all_tasks() == before, "host/client/lifespan task survived"
    finally:
        listener.close()
    assert listener.fileno() == -1
    assert state.loops == {id(asyncio.get_running_loop())}
    assert all(pool.closed for pool in state.pools)
    assert all(ledger.closed for ledger in state.ledgers)
    assert state.lifecycle[-3:] == ["requests.drained", "container.close", "lifespan.close"]


def params(value: Any) -> dict[str, Any]:
    return {
        "message": {
            "messageId": "client-id",
            "role": "ROLE_USER",
            "parts": [{"data": {"value": value}}],
        }
    }


def envelope(value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": "test", "method": "SendMessage", "params": params(value)}


def category(body: dict[str, Any]) -> str:
    return body["error"]["data"][0]["metadata"]["agnaraCode"]


async def official(http: httpx.AsyncClient, url: str, value: int) -> int | float:
    response = await http.get("/.well-known/agent-card.json")
    response.raise_for_status()
    card = json_format.ParseDict(response.json(), a2a_pb2.AgentCard())
    assert len(card.supported_interfaces) == 1
    assert card.supported_interfaces[0].url == url
    assert card.supported_interfaces[0].protocol_version == "1.0"
    async with JsonRpcTransport(http, card, url, is_shared_httpx=True) as client:
        result = await client.send_message(
            json_format.ParseDict(params(value), a2a_pb2.SendMessageRequest())
        )
    message = json_format.MessageToDict(result.message)
    assert message["messageId"] != "client-id" and message["role"] == "ROLE_AGENT"
    assert "taskId" not in message and "contextId" not in message
    return message["parts"][0]["data"]["result"]


def test_pinned_host_real_client_refusals_deadline_and_recovery() -> None:
    assert version("uvicorn") == "0.52.4"

    async def scenario():
        async with serve() as (url, state, _):
            async with httpx.AsyncClient(
                base_url=url, headers=HEADERS, trust_env=False, timeout=5
            ) as http:
                missing = await http.post("/", content=b"{", headers={"Authorization": "unknown"})
                assert missing.status_code == 401
                assert missing.headers["www-authenticate"] == 'Bearer realm="loopback"'
                malformed = await http.post("/", content=b"{")
                assert malformed.json()["error"]["code"] == -32700
                invalid = await http.post("/", json=envelope("bad"))
                assert category(invalid.json()) == "invalid_input"
                denied = await http.post(
                    "/", json=envelope(3), headers={"Authorization": "Bearer fixture-unscoped"}
                )
                assert category(denied.json()) == "forbidden"
                assert state.effects == []
                assert await official(http, url, 3) == 6
                timed_out = await http.post("/", json=envelope(-1))
                assert category(timed_out.json()) == "timeout"
                assert await official(http, url, 4) == 8
                assert state.principals == ["reader"] * 3
                assert state.metadata == [{"transport": "a2a"}] * 3
            assert http.is_closed
        assert state.effects[-1] == "pool.close"
        assert state.effects.count("ledger.close") == 3
        assert state.effects.count("handler.cancel") == 1

    asyncio.run(scenario())


async def raw_client(url: str, body: bytes, content_length: int):
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    reader, writer = await asyncio.open_connection(parsed.hostname, parsed.port)
    headers = (
        f"POST / HTTP/1.1\r\nHost: {parsed.netloc}\r\n"
        "Authorization: Bearer fixture-reader\r\nA2A-Version: 1.0\r\n"
        f"Content-Type: application/json\r\nContent-Length: {content_length}\r\n\r\n"
    )
    writer.write(headers.encode() + body)
    await writer.drain()
    return reader, writer


def test_disconnect_mid_body_never_acquires_application_resources() -> None:
    async def scenario():
        async with serve() as (url, state, _):
            _, writer = await raw_client(url, b"{", 1000)
            try:
                await state.body_received.wait()
            finally:
                writer.close()
                await writer.wait_closed()
            await state.request_closed.wait()
            assert writer.is_closing() and state.disconnect_received.is_set()
            assert state.effects == [] and state.outcomes == [] and state.active == 0

    asyncio.run(scenario())


def test_disconnect_after_handler_entry_cleans_up_at_kernel_deadline() -> None:
    async def scenario():
        async with serve() as (url, state, _):
            payload = json.dumps(envelope(-1)).encode()
            _, writer = await raw_client(url, payload, len(payload))
            try:
                await state.entered.wait()
            finally:
                writer.close()
                await writer.wait_closed()
            await state.request_closed.wait()
            # This host did NOT cancel the request task on disconnect: the
            # kernel reached its deadline and the SDK built a timeout reply,
            # which Uvicorn drops because the peer has already gone away.
            assert category(state.outcomes[-1]) == "timeout"
            assert state.effects == [
                "pool.open",
                "ledger.open",
                "handler.enter",
                "handler.cancel",
                "handler.close",
                "ledger.close",
            ]
            assert state.active == 0
            async with httpx.AsyncClient(base_url=url, headers=HEADERS, trust_env=False) as http:
                assert await official(http, url, 5) == 10
        assert state.effects[-1] == "pool.close"

    asyncio.run(scenario())


def test_graceful_shutdown_drains_active_request_before_container_close() -> None:
    async def scenario():
        async with serve(timeout=5) as (url, state, server):
            async with httpx.AsyncClient(
                base_url=url, headers=HEADERS, trust_env=False, timeout=10
            ) as http:
                async with asyncio.TaskGroup() as owned:
                    request = owned.create_task(http.post("/", json=envelope(-2)))
                    await state.entered.wait()
                    server.should_exit = True
                    while any(s.is_serving() for s in server.servers):
                        await asyncio.sleep(0.01)
                    assert not state.pools[0].closed and not state.ledgers[0].closed
                    state.release.set()
                assert (
                    request.result().json()["result"]["message"]["parts"][0]["data"]["result"] == -4
                )
            assert http.is_closed
        assert "handler.cancel" not in state.effects
        assert state.effects[-3:] == ["handler.close", "ledger.close", "pool.close"]
        assert state.lifecycle.index("request.close") < state.lifecycle.index("container.close")

    asyncio.run(scenario())
