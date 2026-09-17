"""Minimal Litestar owner of routing and lifecycle around an Agnara runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from litestar import Litestar, Request, get, post
from litestar.params import FromPath
from litestar.response import Response

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
_RETRY = "fixture-duplicate"


class Codec:
    def encode(self, value: object, /) -> bytes:
        return json.dumps(value).encode()

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


@dataclass(slots=True)
class State:
    effects: int = 0
    closes: int = 0
    runtime: CapabilityRuntime | None = None
    container: DIContainer | None = None
    store: InMemoryIdempotencyStore = field(default_factory=InMemoryIdempotencyStore)


class Host:
    def __init__(self, state: State) -> None:
        self.state = state
        project, app = Agnara("litestar_fixture"), App("fixture")

        @app.capability(scopes=(_SCOPE,))
        def echo(value: str) -> str:
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
        def failure() -> str:
            raise RuntimeError("host exception must not cross")

        project.include(app)
        caps = project.compile()
        registry = DIRegistry()
        container = DIContainer(registry)
        state.runtime, state.container = (
            CapabilityRuntime(
                caps, tuple(ExecutionPlan.compile(caps[key], registry) for key in caps), container
            ),
            container,
        )

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


def _response(result: Success[object] | Failure) -> Response:
    if isinstance(result, Success):
        return Response(content={"ok": True, "value": result.value})
    status = 403 if result.code.value == "forbidden" else 400
    return Response(content={"ok": False, "code": result.code.value}, status_code=status)


def create_application(state: State | None = None) -> tuple[Litestar, Host]:
    host = Host(state or State())

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

    return Litestar(route_handlers=[native, echo, compose, failure, write]), host
