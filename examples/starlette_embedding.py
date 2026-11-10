"""Native Starlette routes around an owned Agnara capability runtime.

Run: uv run python examples/starlette_embedding.py
Starlette is an optional host fixture; see docs/STARLETTE_EMBEDDING.md.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

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


def failure_response(result: Failure) -> JSONResponse:
    """Host mappings for the failures this complete-result example handles."""
    statuses = {
        FailureCode.FORBIDDEN: 403,
        FailureCode.INVALID_INPUT: 422,
        FailureCode.TIMEOUT: 504,
        FailureCode.CONFLICT: 409,
    }
    return JSONResponse({"error": str(result.code)}, status_code=statuses.get(result.code, 500))


def build_host(state: State | None = None) -> Starlette:
    state = State() if state is None else state

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
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
            yield
        finally:
            # The host must first drain or cancel and await its invocations.
            await runtime.aclose()
            state.observe("runtime.close")
            state.runtime = state.container = None

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def summary(request: Request) -> JSONResponse:
        principal = authenticate(request.headers.get("authorization"))
        if principal is None:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        try:
            payload = await request.json()
        except ValueError, UnicodeDecodeError:
            return JSONResponse({"error": "malformed_json"}, status_code=400)
        if not isinstance(payload, dict):
            return JSONResponse({"error": "object_required"}, status_code=400)
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
            return JSONResponse(result.value)
        return failure_response(result)

    return Starlette(
        routes=[Route("/health", health), Route("/orders", summary, methods=["POST"])],
        lifespan=lifespan,
    )


async def drive(
    host: Any,
    *,
    body: bytes = b'{"order_id":7}',
    credential: str | None = "Bearer token-alice",
    path: str = "/orders",
) -> tuple[int, bytes]:
    """Await a complete ASGI request without a server or HTTP client dependency."""
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: dict[str, Any]) -> None:
        sent.append(dict(message))

    headers = [(b"content-type", b"application/json")]
    if credential is not None:
        headers.append((b"authorization", credential.encode("ascii")))
    await host(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET" if path == "/health" else "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    return int(start["status"]), b"".join(message.get("body", b"") for message in sent)


async def main() -> None:
    state = State()
    host = build_host(state)
    async with host.router.lifespan_context(host):
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
