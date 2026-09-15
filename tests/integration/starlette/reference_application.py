"""A clean, deliberately small Starlette host for ADR 0094.

This module belongs to the integration fixture, never to an Agnara package.
The host retains a runtime explicitly in its lifespan and only translates
verified host values at the route boundary. Capability handlers therefore do
not receive Starlette's request, response, state, or authentication objects.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from agnara import Agnara, AnonymousPrincipal, App, Principal
from agnara.capability import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
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
_TRUSTED_RETRY_TOKEN = "fixture-duplicate"


class JsonCodec:
    """Fixture-owned result serialization for the explicit idempotency port."""

    def encode(self, value: object, /) -> bytes:
        return json.dumps(value, sort_keys=True).encode("utf-8")

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


@dataclass(slots=True)
class FixtureState:
    """Observable host-owned lifecycle state; never injected into a handler."""

    starts: int = 0
    stops: int = 0
    effects: int = 0
    cancellations: int = 0
    runtime: CapabilityRuntime | None = None
    container: DIContainer | None = None
    store: InMemoryIdempotencyStore = field(default_factory=InMemoryIdempotencyStore)


def _principal(request: Request) -> Principal:
    """Map one host-authenticated fixture identity, failing closed otherwise."""

    if request.headers.get("x-fixture-auth") == "reader":
        return Principal("fixture-reader", scopes=(_SCOPE,))
    return AnonymousPrincipal()


def _trusted_idempotency(request: Request, principal: Principal) -> IdempotencyInvocation | None:
    """Accept one pre-verified fixture retry signal, never arbitrary metadata."""

    if (
        principal.identity != "fixture-reader"
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
    if isinstance(result, Success):
        return JSONResponse({"ok": True, "value": result.value})
    if result.code.value == "forbidden":
        status = 403
    elif result.code.value == "conflict":
        status = 409
    else:
        status = 400
    return JSONResponse({"ok": False, "code": result.code.value}, status_code=status)


async def invoke_from_host(
    state: FixtureState,
    capability: str,
    payload: dict[str, Any],
    principal: Principal,
    *,
    idempotency: IdempotencyInvocation | None = None,
) -> Success[object] | Failure:
    """The complete-result bridge ADR 0094 makes host fixtures share."""

    assert state.runtime is not None
    assert state.container is not None
    context = ExecutionContext(
        Invocation(CapabilityId.parse(capability), payload, {}),
        state.container,
        principal=principal,
        idempotency=idempotency,
    )
    return await state.runtime.invoke_result(context)


def _runtime(state: FixtureState) -> tuple[CapabilityRuntime, DIContainer]:
    app = Agnara("fixture_project")
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
        yield "unreachable"

    @fixture.capability(scopes=(_SCOPE,))
    async def slow() -> str:
        try:
            await asyncio.Event().wait()
            return "completed"
        finally:
            state.cancellations += 1

    app.include(fixture)
    capabilities = app.compile()
    registry = DIRegistry()
    plans = tuple(
        ExecutionPlan.compile(capabilities[identifier], registry) for identifier in capabilities
    )
    container = DIContainer(registry)
    return CapabilityRuntime(capabilities, plans, container), container


def create_application(state: FixtureState | None = None) -> Starlette:
    """Create a host with native and Agnara routes in one lifespan."""

    fixture_state = state or FixtureState()

    @asynccontextmanager
    async def lifespan(app: Starlette):
        del app
        fixture_state.starts += 1
        runtime, container = _runtime(fixture_state)
        fixture_state.runtime = runtime
        fixture_state.container = container
        try:
            yield
        finally:
            await runtime.aclose()
            fixture_state.runtime = None
            fixture_state.container = None
            fixture_state.stops += 1

    async def native(_: Request) -> JSONResponse:
        return JSONResponse({"native": "starlette"})

    async def echo(request: Request) -> Response:
        result = await invoke_from_host(
            fixture_state,
            "fixture.echo",
            {"value": request.path_params["value"]},
            _principal(request),
        )
        return _result_response(result)

    async def compose(request: Request) -> Response:
        result = await invoke_from_host(fixture_state, "fixture.compose", {}, _principal(request))
        return _result_response(result)

    async def write(request: Request) -> Response:
        principal = _principal(request)
        result = await invoke_from_host(
            fixture_state,
            "fixture.write",
            {},
            principal,
            idempotency=_trusted_idempotency(request, principal),
        )
        return _result_response(result)

    async def failure(request: Request) -> Response:
        result = await invoke_from_host(fixture_state, "fixture.failure", {}, _principal(request))
        return _result_response(result)

    async def stream(request: Request) -> Response:
        result = await invoke_from_host(fixture_state, "fixture.stream", {}, _principal(request))
        return _result_response(result)

    async def disconnect(request: Request) -> Response:
        # Request handling stays entirely on the host side. Runtime work is a
        # structured child and cancellation reaches its capability.
        await request.body()
        task = asyncio.create_task(
            invoke_from_host(fixture_state, "fixture.slow", {}, _principal(request))
        )
        await asyncio.sleep(0)
        if await request.is_disconnected():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return Response(status_code=499)
        raise AssertionError("fixture disconnect did not cancel the runtime invocation")

    application = Starlette(
        routes=(
            Route("/native", native),
            Route("/agnara/echo/{value}", echo),
            Route("/agnara/compose", compose),
            Route("/agnara/write", write, methods=["POST"]),
            Route("/agnara/failure", failure),
            Route("/agnara/stream", stream),
            Route("/agnara/disconnect", disconnect, methods=["POST"]),
        ),
        lifespan=lifespan,
    )
    application.state.fixture = fixture_state
    return application
