"""Minimal Litestar owner of routing and lifecycle around an Agnara runtime."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from litestar import Litestar, Request, get, post
from litestar.params import FromPath
from litestar.response import Response

from agnara import Agnara, AnonymousPrincipal, App, CapabilityId, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    IdempotencyInvocation,
    IdempotencyScope,
    InMemoryIdempotencyStore,
    Invocation,
    Success,
)

_SCOPE = "fixture:invoke"
_RETRY = "fixture-duplicate"


class Codec:
    def encode(self, value: object, /) -> bytes:
        return json.dumps(value).encode()

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


@dataclass(slots=True)
class Connection:
    """Local lifecycle probe, not a database connection or host object."""

    closed: bool = False


@dataclass(slots=True)
class Session:
    connection: Connection
    closed: bool = False


@dataclass(slots=True)
class State:
    effects: int = 0
    starts: int = 0
    closes: int = 0
    runtime: CapabilityRuntime | None = None
    container: DIContainer | None = None
    store: InMemoryIdempotencyStore = field(default_factory=InMemoryIdempotencyStore)
    # Observe loop identities in host-owned state, never inject a loop object.
    events: list[tuple[str, int]] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)


class Host:
    def __init__(self, state: State) -> None:
        self.state = state

    def record(self, event: str) -> None:
        self.state.events.append((event, id(asyncio.get_running_loop())))

    async def start(self) -> None:
        assert self.state.runtime is None and self.state.container is None
        state = self.state
        project, app = Agnara("litestar_fixture"), App("fixture")

        @provider(scope=Scope.SINGLETON)
        async def connection() -> AsyncIterator[Connection]:
            resource = Connection()
            state.connections.append(resource)
            self.record("connection.open")
            try:
                yield resource
            finally:
                resource.closed = True
                self.record("connection.close")

        @provider(scope=Scope.INVOCATION)
        async def session(connection: Connection) -> AsyncIterator[Session]:
            resource = Session(connection)
            state.sessions.append(resource)
            self.record("session.open")
            try:
                yield resource
            finally:
                resource.closed = True
                self.record("session.close")

        @app.capability(scopes=(_SCOPE,))
        def echo(value: str, session: Session, same_session: Session) -> str:
            assert session is same_session
            assert not session.closed and not session.connection.closed
            self.record("echo")
            return f"agnara:{value}"

        @app.capability(scopes=(_SCOPE,))
        async def compose(invoker: CapabilityInvoker) -> str:
            result = await invoker.invoke(CapabilityId.parse("fixture.echo"), {"value": "child"})
            assert isinstance(result, Success)
            return f"composed:{result.value}"

        @app.capability(scopes=(_SCOPE,), idempotent=True)
        def write() -> int:
            state.effects += 1
            return state.effects

        @app.capability(scopes=(_SCOPE,))
        def failure(session: Session) -> str:
            assert not session.closed and not session.connection.closed
            self.record("failure")
            raise RuntimeError("host exception must not cross")

        project.include(app)
        caps = project.compile()
        registry = DIRegistry()
        registry.bind(Connection, connection)
        registry.bind(Session, session)
        container = DIContainer(registry)
        state.runtime, state.container = (
            CapabilityRuntime(
                caps, tuple(ExecutionPlan.compile(caps[key], registry) for key in caps), container
            ),
            container,
        )
        state.starts += 1
        self.record("startup")

    def principal(self, request: Request[Any, Any, Any]) -> Principal:
        return (
            Principal("litestar-reader", scopes=(_SCOPE,))
            if request.headers.get("x-fixture-auth") == "reader"
            else AnonymousPrincipal()
        )

    async def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        request: Request[Any, Any, Any],
        *,
        idem: IdempotencyInvocation | None = None,
    ) -> Success[object] | Failure:
        assert self.state.runtime and self.state.container
        return await self.state.runtime.invoke_result(
            ExecutionContext(
                Invocation(CapabilityId.parse(capability), payload, {}),
                self.state.container,
                principal=self.principal(request),
                idempotency=idem,
            )
        )

    async def close(self) -> None:
        if self.state.runtime is not None:
            await self.state.runtime.aclose()
            self.state.runtime = None
            self.state.container = None
            self.state.closes += 1
            self.record("shutdown")


def _response(result: Success[object] | Failure) -> Response:
    if isinstance(result, Success):
        return Response(content={"ok": True, "value": result.value})
    status = 403 if result.code.value == "forbidden" else 400
    return Response(content={"ok": False, "code": result.code.value}, status_code=status)


def create_application(state: State | None = None) -> tuple[Litestar, Host]:
    host = Host(state or State())

    @asynccontextmanager
    async def lifespan(_: Litestar) -> AsyncIterator[None]:
        await host.start()
        try:
            yield
        finally:
            # Litestar owns this lifespan; calls have finished before shutdown.
            await host.close()

    @get("/native")
    async def native() -> dict[str, str]:
        return {"native": "litestar"}

    @get("/agnara/echo/{value:str}")
    async def echo(request: Request, value: FromPath[str]) -> Response:
        return _response(await host.invoke("fixture.echo", {"value": value}, request))

    @get("/agnara/compose")
    async def compose(request: Request) -> Response:
        return _response(await host.invoke("fixture.compose", {}, request))

    @get("/agnara/failure")
    async def failure(request: Request) -> Response:
        return _response(await host.invoke("fixture.failure", {}, request))

    @post("/agnara/write", status_code=200)
    async def write(request: Request) -> Response:
        principal = host.principal(request)
        idem = None
        if (
            principal.identity == "litestar-reader"
            and request.headers.get("x-fixture-retry") == _RETRY
        ):
            idem = IdempotencyInvocation(
                IdempotencyScope(
                    CapabilityId.parse("fixture.write"), principal.identity, _RETRY, b"v1"
                ),
                host.state.store,
                Codec(),
                30,
                60,
            )
        return _response(await host.invoke("fixture.write", {}, request, idem=idem))

    return Litestar(
        route_handlers=[native, echo, compose, failure, write], lifespan=[lifespan]
    ), host
