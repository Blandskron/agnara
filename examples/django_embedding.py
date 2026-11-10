"""Django async views around an owned Agnara capability runtime.

Run: uv run python examples/django_embedding.py
Django is an optional host fixture; see docs/DJANGO_EMBEDDING.md.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import django
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.test import AsyncRequestFactory

from agnara import Agnara, CapabilityId, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    Success,
)


@dataclass
class Audit:
    """Application port; the handler never receives a host request or credential."""

    orders: list[int] = field(default_factory=list)

    async def record(self, order_id: int) -> None:
        self.orders.append(order_id)


@dataclass
class State:
    audit: Audit = field(default_factory=Audit)
    events: list[tuple[str, int]] = field(default_factory=list)
    runtime: CapabilityRuntime | None = None
    container: DIContainer | None = None

    def observe(self, name: str) -> None:
        self.events.append((name, id(asyncio.get_running_loop())))


def authenticate(header: str | None) -> Principal | None:
    """Demonstration credentials only; replace with trusted host verification."""
    tokens = {
        "token-alice": Principal("alice", scopes={"orders:read"}),
        "token-bob": Principal("bob"),
    }
    if header is None:
        return None
    scheme, separator, token = header.partition(" ")
    if scheme.lower() != "bearer" or not separator:
        return None
    return tokens.get(token)


def build_application() -> Agnara:
    app = Agnara("orders")

    @app.capability(scopes={"orders:read"}, output=dict[str, int])
    async def summary(order_id: int, audit: Audit) -> dict[str, int]:
        await audit.record(order_id)
        return {"order_id": order_id}

    return app


def failure_response(result: Failure) -> JsonResponse:
    """Host mappings for the failures this complete-result example handles."""
    statuses = {
        FailureCode.FORBIDDEN: 403,
        FailureCode.INVALID_INPUT: 422,
        FailureCode.TIMEOUT: 504,
        FailureCode.CONFLICT: 409,
    }
    return JsonResponse({"error": str(result.code)}, status=statuses.get(result.code, 500))


def configure_demo() -> None:
    """Initialize only this standalone fixture; real projects own their settings."""
    if not settings.configured:
        settings.configure(DEFAULT_CHARSET="utf-8", USE_I18N=False)
        django.setup()


class Host:
    """Application-owned view handle, not a Django ASGI or lifespan adapter."""

    def __init__(self, state: State) -> None:
        self.state = state

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[Host]:
        state = self.state
        app = build_application()
        capabilities = app.compile()
        dependencies = DIRegistry()

        @provider(scope=Scope.SINGLETON)
        async def audit() -> AsyncIterator[Audit]:
            state.observe("audit.open")
            try:
                yield state.audit
            finally:
                state.observe("audit.close")

        dependencies.bind(Audit, audit)
        plans = [ExecutionPlan.compile(item, dependencies) for item in capabilities.values()]
        container = DIContainer(dependencies)
        runtime = CapabilityRuntime(capabilities, plans, container)
        state.container, state.runtime = container, runtime
        state.observe("runtime.open")
        try:
            yield self
        finally:
            # The host must first drain or cancel and await its invocations.
            await runtime.aclose()
            state.observe("runtime.close")
            state.runtime = state.container = None

    async def health(self, request: HttpRequest) -> JsonResponse:
        if request.method != "GET":
            return JsonResponse(
                {"error": "method_not_allowed"}, status=405, headers={"Allow": "GET"}
            )
        return JsonResponse({"status": "ok"})

    async def summary(self, request: HttpRequest) -> JsonResponse:
        if request.method != "POST":
            return JsonResponse(
                {"error": "method_not_allowed"}, status=405, headers={"Allow": "POST"}
            )
        state = self.state
        principal = authenticate(request.headers.get("authorization"))
        if principal is None:
            return JsonResponse({"error": "unauthenticated"}, status=401)
        try:
            payload = json.loads(request.body)
        except ValueError, UnicodeDecodeError:
            return JsonResponse({"error": "malformed_json"}, status=400)
        if not isinstance(payload, dict):
            return JsonResponse({"error": "object_required"}, status=400)
        assert state.runtime is not None and state.container is not None
        # Native request and credential stop here; only payload/principal cross.
        state.observe("invoke")
        result = await state.runtime.invoke_result(
            ExecutionContext(
                Invocation(CapabilityId.parse("orders.summary"), payload, {}),
                state.container,
                principal=principal,
            )
        )
        if isinstance(result, Success):
            return JsonResponse(result.value)
        return failure_response(result)


def build_host(state: State | None = None) -> Host:
    return Host(State() if state is None else state)


async def drive(
    host: Host,
    *,
    body: bytes = b'{"order_id":7}',
    credential: str | None = "Bearer token-alice",
    path: str = "/orders",
    method: str | None = None,
) -> tuple[int, bytes]:
    """Await a native view with a test request; no URL resolver or middleware."""
    headers = {} if credential is None else {"authorization": credential}
    request = AsyncRequestFactory().generic(
        method or ("GET" if path == "/health" else "POST"),
        path,
        data=body,
        content_type="application/json",
        headers=headers,
    )
    response = await (host.health(request) if path == "/health" else host.summary(request))
    return response.status_code, bytes(response.content)


async def main() -> None:
    configure_demo()
    state = State()
    host = build_host(state)
    async with host.lifespan():
        cases = [
            ("success", b'{"order_id":7}', "Bearer token-alice"),
            ("policy denial", b'{"order_id":8}', "Bearer token-bob"),
            ("unknown credential", b'{"order_id":9}', "Bearer unknown"),
            ("missing credential", b'{"order_id":9}', None),
            ("malformed JSON", b"{", "Bearer token-alice"),
            ("invalid input", b'{"order_id":"bad"}', "Bearer token-alice"),
        ]
        for label, body, credential in cases:
            status, response = await drive(host, body=body, credential=credential)
            print(f"{label}: {status} {response.decode()}")
        status, response = await drive(host, path="/health", credential=None)
        print(f"native health: {status} {response.decode()}")
    print(f"recorded orders: {state.audit.orders}")
    print(f"cleanup: {[name for name, _ in state.events][-2:]}")


if __name__ == "__main__":
    asyncio.run(main())
