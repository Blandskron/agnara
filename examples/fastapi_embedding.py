"""Agnara — embedded inside an existing FastAPI application.

    python fastapi_embedding.py

This is progressive adoption: FastAPI keeps its routes, its dependencies and
its error handling, and Agnara runs capabilities beside them in the same event
loop. Nothing is mounted and no ASGI app is replaced.

ADR 0094 defines the boundary, and the division of labour is the whole point:

* The **host** owns its request, its authentication and its response mapping.
  It decides whether a request produces a principal at all.
* The **host** owns lifecycle. It compiles capabilities once at startup and
  closes the dependency container at shutdown.
* **Agnara** owns execution. It receives a payload and a principal, and returns
  a canonical `Success` or `Failure`.

Two rules this example exists to show. The host's request object never reaches a
capability: `authenticate` turns a header into a `Principal` and the capability
sees only that. And identity mapping fails closed -- a missing or unrecognised
credential yields no principal, so a scoped capability is refused rather than
executed anonymously.

Requires `fastapi` in the environment; it is not an Agnara dependency and never
becomes one.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from agnara import Agnara, App
from agnara.capability import CapabilityRegistry
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
)
from agnara.policy import Principal

#: A credential store stands in for whatever the host really uses.
_TOKENS = {"token-alice": ("alice", {"orders:read"}), "token-bob": ("bob", set())}


@dataclass
class Embedded:
    """What the host builds at startup and closes at shutdown."""

    runtime: CapabilityRuntime | None = None
    container: DIContainer | None = None
    plans: dict[str, ExecutionPlan] = field(default_factory=dict)


def build_application() -> App:
    app = App("orders")

    @app.capability(scopes={"orders:read"})
    def summary(order_id: str) -> dict[str, str]:
        return {"order": order_id, "status": "shipped"}

    return app


def compile_embedded() -> Embedded:
    project = Agnara("shop")
    project.include(build_application())
    capabilities = project.compile()

    registry = DIRegistry()
    plans = [ExecutionPlan.compile(definition, registry) for definition in capabilities.values()]
    container = DIContainer(registry)
    frozen = CapabilityRegistry(plan.definition for plan in plans).freeze()

    return Embedded(
        runtime=CapabilityRuntime(frozen, plans, container),
        container=container,
        plans={str(plan.definition.id): plan for plan in plans},
    )


def authenticate(authorization: str | None) -> Principal | None:
    """Map a host credential to a principal, or to nothing.

    Returning `None` rather than an anonymous principal is the fail-closed half
    of the boundary. A mapper must never invent scopes, confirmation evidence or
    execution identity from request data.
    """
    if authorization is None:
        return None
    entry = _TOKENS.get(authorization.removeprefix("Bearer ").strip())
    if entry is None:
        return None
    identity, scopes = entry
    return Principal(identity, scopes=scopes)


def build_host() -> FastAPI:
    embedded = Embedded()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Compiled once. A runtime snapshot is immutable, so nothing
        # recompiles per request.
        built = compile_embedded()
        embedded.runtime, embedded.container, embedded.plans = (
            built.runtime,
            built.container,
            built.plans,
        )
        try:
            yield
        finally:
            if embedded.container is not None:
                await embedded.container.aclose()
            embedded.runtime = embedded.container = None

    host = FastAPI(lifespan=lifespan)

    @host.get("/health")
    async def health() -> dict[str, str]:
        """An ordinary FastAPI route, untouched by Agnara."""
        return {"status": "ok"}

    @host.get("/orders/{order_id}")
    async def order_summary(
        order_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        principal = authenticate(authorization)
        if principal is None:
            # The host owns this decision and this status code. Agnara has no
            # opinion about 401.
            raise HTTPException(status_code=401, detail="unauthenticated")

        assert embedded.runtime is not None and embedded.container is not None
        plan = embedded.plans["orders.summary"]

        # `request` stops here. The capability receives a payload and a
        # principal, never the host's request, session or transaction.
        result = await embedded.runtime.invoke_result(
            ExecutionContext(
                Invocation(plan.definition.id, {"order_id": order_id}, {}),
                embedded.container,
                principal=principal,
                tracking_id=request.headers.get("x-request-id"),
            )
        )

        if isinstance(result, Success):
            return JSONResponse(result.value)
        # The host maps a canonical failure to its own wire shape. The failure
        # is already redacted, so this cannot leak handler detail.
        return JSONResponse({"error": str(result.code)}, status_code=403)

    return host


async def drive(host: Any, path: str, headers: dict[str, str]) -> tuple[int, bytes]:
    """Drive the ASGI app directly, so the example needs no server."""
    sent: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: dict[str, Any]) -> None:
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
            "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent)
    return int(start["status"]), body


async def main() -> None:
    host = build_host()

    async with host.router.lifespan_context(host):
        for label, headers in (
            ("authorized, scoped", {"authorization": "Bearer token-alice"}),
            ("authenticated, missing scope", {"authorization": "Bearer token-bob"}),
            ("unknown credential", {"authorization": "Bearer nope"}),
            ("no credential", {}),
        ):
            status, body = await drive(host, "/orders/A-1", headers)
            print(f"{label:<30} -> {status} {body.decode()}")

        status, body = await drive(host, "/health", {})
        print(f"{'plain FastAPI route':<30} -> {status} {body.decode()}")

    print("\nThe capability never saw the request object, and an unmapped")
    print("credential was refused rather than executed anonymously.")


if __name__ == "__main__":
    asyncio.run(main())
