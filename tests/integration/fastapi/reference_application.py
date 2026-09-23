"""A deliberately small FastAPI host exercising the public embedding boundary.

FastAPI retains routing, dependencies, security mapping, exception handling and
the outer lifespan. Agnara receives only schema-bound values and a verified
``Principal``; neither its handlers nor its DI graph receive FastAPI objects.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, MutableMapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response

from agnara import Agnara, AnonymousPrincipal, App, Principal
from agnara.capability import CapabilityId
from agnara.di import DIContainer, DIRegistry
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
from agnara_http import Binding, BindingSource, Http, HttpApplication, OpenApiInfo, OpenApiOperation

_SCOPE = "fixture:invoke"
_TRUSTED_RETRY_TOKEN = "fixture-duplicate"


class JsonCodec:
    """Fixture-owned codec for the explicit idempotency port."""

    def encode(self, value: object, /) -> bytes:
        return json.dumps(value, sort_keys=True).encode("utf-8")

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


@dataclass(frozen=True, slots=True)
class VerifiedActor:
    """A host-authenticated identity, intentionally not an Agnara value."""

    subject: str


class NativeFailure(Exception):
    """A FastAPI-only failure used to prove native exception ownership."""


class FixtureHeaderMiddleware:
    """A host-owned ASGI middleware that never translates Agnara outcomes."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        async def send_with_header(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                message = {
                    **message,
                    "headers": [*message["headers"], (b"x-fixture-middleware", b"active")],
                }
            await send(message)

        await self.app(scope, receive, send_with_header)


@dataclass(slots=True)
class _MountedLifespan:
    """One explicitly owned ASGI child lifespan, joined during host shutdown."""

    incoming: asyncio.Queue[dict[str, Any]]
    outgoing: asyncio.Queue[dict[str, Any]]
    task: asyncio.Task[None]
    group: asyncio.TaskGroup

    async def close(self) -> None:
        await self.incoming.put({"type": "lifespan.shutdown"})
        message = await self.outgoing.get()
        assert message["type"] == "lifespan.shutdown.complete"
        await self.task
        await self.group.__aexit__(None, None, None)


@dataclass(slots=True)
class FixtureState:
    """Observable host-owned state; capability handlers cannot see it."""

    starts: int = 0
    stops: int = 0
    projected_starts: int = 0
    projected_stops: int = 0
    effects: int = 0
    cancellations: int = 0
    runtime: CapabilityRuntime | None = None
    container: DIContainer | None = None
    projected: HttpApplication | None = None
    mounted_lifespan: _MountedLifespan | None = None
    store: InMemoryIdempotencyStore = field(default_factory=InMemoryIdempotencyStore)


async def verified_actor(
    x_fixture_auth: Annotated[str | None, Header()] = None,
) -> VerifiedActor | None:
    """Verify a fixed fixture credential; headers never manufacture scopes."""

    if x_fixture_auth == "reader":
        return VerifiedActor("fastapi-reader")
    return None


def _principal(actor: VerifiedActor | None) -> Principal:
    if actor is None:
        return AnonymousPrincipal()
    return Principal(actor.subject, scopes=(_SCOPE,))


def _trusted_idempotency(
    request: Request,
    principal: Principal,
) -> IdempotencyInvocation | None:
    """Only the verified actor plus one fixture signal can select replay."""

    if (
        principal.identity != "fastapi-reader"
        or request.headers.get("x-fixture-retry") != _TRUSTED_RETRY_TOKEN
    ):
        return None
    return IdempotencyInvocation(
        IdempotencyScope(
            CapabilityId.parse("fixture.write"),
            principal.identity,
            _TRUSTED_RETRY_TOKEN,
            b"fixture-write-v1",
        ),
        request.app.state.fixture.store,
        JsonCodec(),
        30,
        60,
    )


def _result_response(result: Success[object] | Failure) -> JSONResponse:
    """Map only canonical results outward; no host exception crosses inward."""

    if isinstance(result, Success):
        return JSONResponse({"ok": True, "value": result.value})
    status = (
        403 if result.code.value == "forbidden" else 409 if result.code.value == "conflict" else 400
    )
    return JSONResponse({"ok": False, "code": result.code.value}, status_code=status)


async def invoke_from_host(
    state: FixtureState,
    capability: str,
    payload: dict[str, Any],
    principal: Principal,
    *,
    idempotency: IdempotencyInvocation | None = None,
) -> Success[object] | Failure:
    """The complete-result bridge from ADR 0094, expressed in FastAPI."""

    assert state.runtime is not None
    assert state.container is not None
    context = ExecutionContext(
        Invocation(CapabilityId.parse(capability), payload, {}),
        state.container,
        principal=principal,
        idempotency=idempotency,
    )
    return await state.runtime.invoke_result(context)


async def _start_mounted_lifespan(application: HttpApplication) -> _MountedLifespan:
    """Run an ASGI child lifespan explicitly; FastAPI does not do this for mounts."""

    incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    group = asyncio.TaskGroup()
    await group.__aenter__()
    task = group.create_task(
        application(
            {"type": "lifespan", "asgi": {"version": "3.0"}},
            incoming.get,
            outgoing.put,
        )
    )
    await incoming.put({"type": "lifespan.startup"})
    message = await outgoing.get()
    assert message["type"] == "lifespan.startup.complete"
    return _MountedLifespan(incoming, outgoing, task, group)


def _runtime(state: FixtureState) -> tuple[CapabilityRuntime, DIContainer, HttpApplication]:
    application = Agnara("fastapi_fixture")
    fixture = App("fixture")

    @fixture.capability(scopes=(_SCOPE,))
    def echo(value: str) -> str:
        return f"agnara:{value}"

    @fixture.capability(scopes=(_SCOPE,))
    async def compose(invoker: CapabilityInvoker) -> str:
        child = await invoker.invoke(CapabilityId.parse("fixture.echo"), {"value": "child"})
        assert isinstance(child, Success)
        return f"composed:{child.value}"

    @fixture.capability(scopes=(_SCOPE,), idempotent=True)
    def write() -> int:
        state.effects += 1
        return state.effects

    @fixture.capability(scopes=(_SCOPE,))
    def failure() -> str:
        raise RuntimeError("fixture secret must not cross the host boundary")

    @fixture.capability(scopes=(_SCOPE,), streaming=True)
    async def stream():
        yield "one"
        yield "two"

    @fixture.capability
    def projected_echo(value: str) -> str:
        return f"projected:{value}"

    @fixture.capability(streaming=True)
    async def projected_stream():
        yield "one"
        yield "two"

    @fixture.capability(scopes=(_SCOPE,))
    async def slow() -> str:
        try:
            await asyncio.Event().wait()
            return "completed"
        finally:
            state.cancellations += 1

    application.include(fixture)
    capabilities = application.compile()
    registry = DIRegistry()
    plans = tuple(
        ExecutionPlan.compile(capabilities[identifier], registry) for identifier in capabilities
    )
    container = DIContainer(registry)
    runtime = CapabilityRuntime(capabilities, plans, container)

    @asynccontextmanager
    async def projected_lifecycle():
        state.projected_starts += 1
        try:
            yield
        finally:
            state.projected_stops += 1

    http = Http("fastapi-projected")
    http.get(
        "/echo/{value}",
        projected_echo,
        Binding("value", BindingSource.PATH),
        openapi=OpenApiOperation(summary="Projected echo"),
    )
    http.sse("/events", projected_stream)
    projected = http.compile(
        capabilities,
        openapi=OpenApiInfo("Fixture projected surface", "0"),
        lifecycle=projected_lifecycle,
    )
    return runtime, container, projected


def create_application(state: FixtureState | None = None) -> FastAPI:
    """Create a FastAPI owner with native and Agnara ASGI routes side by side."""

    fixture_state = state or FixtureState()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        fixture_state.starts += 1
        runtime, container, projected = _runtime(fixture_state)
        fixture_state.runtime = runtime
        fixture_state.container = container
        fixture_state.projected = projected
        fixture_state.mounted_lifespan = await _start_mounted_lifespan(projected)
        try:
            yield
        finally:
            mounted = fixture_state.mounted_lifespan
            if mounted is not None:
                await mounted.close()
            await runtime.aclose()
            fixture_state.mounted_lifespan = None
            fixture_state.runtime = None
            fixture_state.container = None
            fixture_state.stops += 1

    host = FastAPI(title="Fixture native API", lifespan=lifespan)

    host.add_middleware(FixtureHeaderMiddleware)

    @host.exception_handler(NativeFailure)
    async def native_failure_handler(_: Request, __: NativeFailure) -> JSONResponse:
        return JSONResponse({"native_error": "handled"}, status_code=418)

    @host.get("/native")
    async def native(
        actor: Annotated[VerifiedActor | None, Depends(verified_actor)],
    ) -> dict[str, str]:
        return {"native": "fastapi", "actor": actor.subject if actor is not None else "anonymous"}

    @host.get("/native/failure")
    async def native_failure() -> None:
        raise NativeFailure()

    @host.get("/agnara/echo/{value}")
    async def echo_route(
        value: str,
        actor: Annotated[VerifiedActor | None, Depends(verified_actor)],
    ) -> JSONResponse:
        return _result_response(
            await invoke_from_host(
                fixture_state, "fixture.echo", {"value": value}, _principal(actor)
            )
        )

    @host.get("/agnara/compose")
    async def compose_route(
        actor: Annotated[VerifiedActor | None, Depends(verified_actor)],
    ) -> JSONResponse:
        return _result_response(
            await invoke_from_host(fixture_state, "fixture.compose", {}, _principal(actor))
        )

    @host.post("/agnara/write")
    async def write_route(
        request: Request,
        actor: Annotated[VerifiedActor | None, Depends(verified_actor)],
    ) -> JSONResponse:
        principal = _principal(actor)
        return _result_response(
            await invoke_from_host(
                fixture_state,
                "fixture.write",
                {},
                principal,
                idempotency=_trusted_idempotency(request, principal),
            )
        )

    @host.get("/agnara/failure")
    async def agnara_failure(
        actor: Annotated[VerifiedActor | None, Depends(verified_actor)],
    ) -> JSONResponse:
        return _result_response(
            await invoke_from_host(fixture_state, "fixture.failure", {}, _principal(actor))
        )

    @host.get("/agnara/stream")
    async def stream_refusal(
        actor: Annotated[VerifiedActor | None, Depends(verified_actor)],
    ) -> JSONResponse:
        return _result_response(
            await invoke_from_host(fixture_state, "fixture.stream", {}, _principal(actor))
        )

    @host.post("/agnara/disconnect")
    async def disconnect(
        request: Request,
        actor: Annotated[VerifiedActor | None, Depends(verified_actor)],
    ) -> Response:
        await request.body()
        task = asyncio.create_task(
            invoke_from_host(fixture_state, "fixture.slow", {}, _principal(actor))
        )
        await asyncio.sleep(0)
        if await request.is_disconnected():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return Response(status_code=499)
        raise AssertionError("fixture disconnect did not cancel the runtime invocation")

    host.mount("/agnara-http", _DeferredMount(fixture_state))
    host.state.fixture = fixture_state
    return host


class _DeferredMount:
    """Resolve the compiled child after FastAPI owns startup, without private APIs."""

    __slots__ = ("_state",)

    def __init__(self, state: FixtureState) -> None:
        self._state = state

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None:
        projected = self._state.projected
        if projected is None:
            raise RuntimeError("FastAPI host received a mounted request before startup")
        await projected(cast(dict[str, Any], scope), receive, send)
