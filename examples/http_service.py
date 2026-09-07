"""Agnara 0.1.0a4 — serving capabilities over HTTP.

Runs against public API only. `docs/HTTP_COMPOSITION.md` is the guide this
mirrors, including the limitations of this release.

    python http_service.py

It composes one HTTP surface, drives four requests through the compiled ASGI
application without a server, prints the generated OpenAPI paths, and shows
that the same capabilities feed the protocol-neutral exposure registry.

`agnara-http` is not published to PyPI in this release, so it must be
installed from a locally built wheel. See the release notes and issue #291.

To serve it for real, hand `asgi` to any ASGI server:

    uvicorn http_service:asgi
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from agnara import Agnara, Risk, StandardEffect
from agnara.core.di import DIRegistry, Scope, provider
from agnara.exposure import compile_exposures
from agnara_http import Binding, BindingSource, Http, OpenApiInfo, OpenApiOperation


class Ledger:
    """A stand-in for whatever the application really talks to."""

    def __init__(self) -> None:
        self._orders: dict[str, dict[str, Any]] = {"A-1": {"sku": "widget", "quantity": 3}}

    def read(self, order_id: str) -> dict[str, Any] | None:
        return self._orders.get(order_id)

    def write(self, order_id: str, order: dict[str, Any]) -> str:
        self._orders[order_id] = order
        return order_id


@provider(scope=Scope.SINGLETON)
def provide_ledger() -> Ledger:
    return Ledger()


dependencies = DIRegistry()
dependencies.bind(Ledger, provide_ledger)

app = Agnara("shop")


@app.capability(description="Read one order.", idempotent=True)
def show_order(order_id: str, ledger: Ledger) -> dict[str, Any]:
    order = ledger.read(order_id)
    if order is None:
        return {"found": False}
    return {"found": True, "order": order}


# `dict[str, Any]` rather than a dataclass: a dataclass-typed body cannot be
# filled from JSON yet, which is a framework defect tracked as issue #296
# rather than something this example works around quietly.
@app.capability(
    description="Create or replace one order.",
    effects=(StandardEffect.EXTERNAL_WRITE,),
    risk=Risk.MEDIUM,
)
def put_order(order_id: str, order: dict[str, Any], ledger: Ledger) -> dict[str, Any]:
    return {"stored": ledger.write(order_id, order)}


@app.capability(description="Report service health.")
def health() -> str:
    return "ok"


# 1. Declare which capabilities this HTTP surface exposes. Bindings are
#    explicit, including for path parameters (ADR 0026).
http = Http("public")
http.get(
    "/orders/{order_id}",
    show_order,
    Binding("order_id", BindingSource.PATH),
    openapi=OpenApiOperation(summary="Show an order", publish_description=True, tags=("orders",)),
)
http.put(
    "/orders/{order_id}",
    put_order,
    Binding("order_id", BindingSource.PATH),
    Binding("order", BindingSource.BODY),
    openapi=OpenApiOperation(summary="Store an order", tags=("orders",)),
)
# No `openapi=`, so this one is served and stays out of the document (ADR 0035).
http.get("/health", health)

# 2. Freeze the capabilities, then compile the surface. Both calls belong to
#    the application: nothing is registered globally.
capabilities = app.compile()
asgi = http.compile(
    capabilities,
    dependencies=dependencies,
    openapi=OpenApiInfo("Shop API", "1.0.0", summary="Orders, over HTTP."),
    openapi_path="/openapi.json",
    request_timeout=5.0,
)


def request(
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: tuple[tuple[bytes, bytes], ...] = (),
) -> tuple[int, bytes]:
    """Drive one request the way an ASGI server would, without running one."""
    events: list[dict[str, Any]] = []
    pending = [{"type": "http.request", "body": b"" if body is None else body, "more_body": False}]

    async def receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": list(headers),
        "root_path": "",
    }
    asyncio.run(asgi(scope, receive, send))
    return events[0]["status"], b"".join(event.get("body", b"") for event in events[1:])


def main() -> None:
    print(f"compiled: {asgi!r}")

    status, payload = request("GET", "/orders/A-1")
    print(f"read     -> {status} {payload.decode()}")

    status, payload = request(
        "PUT",
        "/orders/B-2",
        body=json.dumps({"sku": "gadget", "quantity": 1}).encode("utf-8"),
        headers=((b"content-type", b"application/json"),),
    )
    print(f"write    -> {status} {payload.decode()}")

    # A capability failure is an RFC 9457 problem document, not an exception.
    status, payload = request("GET", "/orders")
    problem = json.loads(payload)
    print(f"missing  -> {status} {problem['code']}")

    status, payload = request("GET", "/openapi.json")
    document = json.loads(payload)
    print(f"openapi  -> {status} {document['openapi']} paths={sorted(document['paths'])}")

    # The undocumented route is served and absent from the document.
    print(f"health   -> {request('GET', '/health')[0]} documented={'/health' in document['paths']}")

    # 3. The same surface feeds the protocol-neutral exposure registry, so one
    #    capability exposed over HTTP and MCP has one answer to where it is
    #    reachable (ADR 0070).
    exposures = compile_exposures(capabilities, [asgi.exposures])
    print(f"exposures-> {[str(identity) for identity in exposures]}")


if __name__ == "__main__":
    main()
