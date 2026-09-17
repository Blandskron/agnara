"""Small Django async-view fixture for the ADR 0094 embedding boundary.

The Django request, user/session and ORM transaction remain host concerns.
Only a verified fixture actor becomes a framework-neutral Principal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse

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


class JsonCodec:
    def encode(self, value: object, /) -> bytes:
        return json.dumps(value, sort_keys=True).encode()

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


@dataclass(frozen=True, slots=True)
class VerifiedActor:
    """Host-authenticated value; neither a Django user nor an Agnara handler input."""

    subject: str


@dataclass(slots=True)
class FixtureState:
    effects: int = 0
    closes: int = 0
    runtime: CapabilityRuntime | None = None
    container: DIContainer | None = None
    store: InMemoryIdempotencyStore = field(default_factory=InMemoryIdempotencyStore)


def _actor(request: HttpRequest) -> VerifiedActor | None:
    """A fixed host verifier: arbitrary headers never grant Agnara scopes."""

    if request.headers.get("X-Fixture-Auth") == "reader":
        return VerifiedActor("django-reader")
    return None


def _principal(actor: VerifiedActor | None) -> Principal:
    return AnonymousPrincipal() if actor is None else Principal(actor.subject, scopes=(_SCOPE,))


def _response(result: Success[object] | Failure) -> JsonResponse:
    if isinstance(result, Success):
        return JsonResponse({"ok": True, "value": result.value})
    status = (
        403 if result.code.value == "forbidden" else 409 if result.code.value == "conflict" else 400
    )
    return JsonResponse({"ok": False, "code": result.code.value}, status=status)


class DjangoHost:
    """Application-owned async host bridge; no runtime is stored globally."""

    def __init__(self, state: FixtureState) -> None:
        self.state = state
        application = Agnara("django_fixture")
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
            raise RuntimeError("Django exception must not cross the canonical boundary")

        application.include(fixture)
        capabilities = application.compile()
        registry = DIRegistry()
        container = DIContainer(registry)
        plans = tuple(ExecutionPlan.compile(capabilities[item], registry) for item in capabilities)
        state.runtime = CapabilityRuntime(capabilities, plans, container)
        state.container = container

    async def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        actor: VerifiedActor | None,
        *,
        idempotency: IdempotencyInvocation | None = None,
    ) -> Success[object] | Failure:
        assert self.state.runtime is not None
        assert self.state.container is not None
        return await self.state.runtime.invoke_result(
            ExecutionContext(
                Invocation(CapabilityId.parse(capability), payload, {}),
                self.state.container,
                principal=_principal(actor),
                idempotency=idempotency,
            )
        )

    async def aclose(self) -> None:
        if self.state.runtime is not None:
            await self.state.runtime.aclose()
            self.state.runtime = None
            self.state.container = None
            self.state.closes += 1

    async def native_view(self, _: HttpRequest) -> JsonResponse:
        return JsonResponse({"native": "django"})

    async def echo_view(self, request: HttpRequest, value: str) -> JsonResponse:
        return _response(await self.invoke("fixture.echo", {"value": value}, _actor(request)))

    async def compose_view(self, request: HttpRequest) -> JsonResponse:
        return _response(await self.invoke("fixture.compose", {}, _actor(request)))

    async def write_view(self, request: HttpRequest) -> JsonResponse:
        actor = _actor(request)
        principal = _principal(actor)
        idempotency = None
        if (
            principal.identity == "django-reader"
            and request.headers.get("X-Fixture-Retry") == _RETRY
        ):
            idempotency = IdempotencyInvocation(
                IdempotencyScope(
                    CapabilityId.parse("fixture.write"), principal.identity, _RETRY, b"v1"
                ),
                self.state.store,
                JsonCodec(),
                30,
                60,
            )
        return _response(await self.invoke("fixture.write", {}, actor, idempotency=idempotency))

    async def failure_view(self, request: HttpRequest) -> JsonResponse:
        return _response(await self.invoke("fixture.failure", {}, _actor(request)))

    async def orm_boundary_view(self, _: HttpRequest) -> HttpResponse:
        """Django retains transaction/ORM ownership; no ORM object enters Agnara."""

        return HttpResponse(status=204)
