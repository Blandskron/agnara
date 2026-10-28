"""Agnara current 1.x — serving capabilities over HTTP.

Runs against public API only. `docs/HTTP_COMPOSITION.md` is the guide this
mirrors, including the limitations of this release.

    python http_service.py

It composes one HTTP surface and owns its startup, requests and shutdown on
one event loop without a server, prints the generated OpenAPI paths, and shows
that the same capabilities feed the protocol-neutral exposure registry.

Install synchronized 1.x packages. The stable public API is documented in
`docs/PUBLIC_API.md`.

To serve it for real, hand `asgi` to any ASGI server:

    uvicorn http_service:asgi
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from agnara import Agnara, Risk, StandardEffect
from agnara.di import DIRegistry, Scope, provider
from agnara.exposure import compile_exposures
from agnara_http import Binding, BindingSource, Http, HttpApplication, OpenApiInfo, OpenApiOperation


class Ledger:
    """A stand-in for whatever the application really talks to."""

    def __init__(self) -> None:
        self.closed = False
        self._orders: dict[str, Order] = {"A-1": Order("widget", 3)}

    def close(self) -> None:
        self.closed = True

    def read(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def write(self, order_id: str, order: Order) -> str:
        self._orders[order_id] = order
        return order_id


@dataclass(frozen=True, slots=True)
class Order:
    """The application input HTTP materializes from the declared JSON shape."""

    sku: str
    quantity: int


@provider(scope=Scope.SINGLETON)
async def provide_ledger() -> AsyncIterator[Ledger]:
    ledger = Ledger()
    try:
        yield ledger
    finally:
        ledger.close()


app = Agnara("shop")


@app.capability(description="Read one order.", idempotent=True)
def show_order(order_id: str, ledger: Ledger) -> dict[str, Any]:
    order = ledger.read(order_id)
    if order is None:
        return {"found": False}
    return {
        "found": True,
        "order": {"sku": order.sku, "quantity": order.quantity},
    }


@app.capability(
    description="Create or replace one order.",
    effects=(StandardEffect.EXTERNAL_WRITE,),
    risk=Risk.MEDIUM,
)
def put_order(order_id: str, order: Order, ledger: Ledger) -> dict[str, Any]:
    return {"stored": ledger.write(order_id, order)}


@app.capability(description="Report service health.")
def health() -> str:
    return "ok"


@app.capability(description="Attach a note and a document to one order.")
def attach(order_id: str, session: str, note: str, document: bytes) -> dict[str, Any]:
    """A cookie, a form field and a bounded in-memory upload."""
    return {
        "order_id": order_id,
        "session": session,
        "note": note,
        # The client filename is never exposed (ADR 0072), so an application
        # names its own artefacts. Here that means reporting a size.
        "bytes": len(document),
    }


# Capabilities are a frozen transport-neutral snapshot; each worker below gets
# a fresh HTTP surface and container. Compiling does not open provider resources.
capabilities = app.compile()


def create_application(dependencies: DIRegistry | None = None) -> HttpApplication:
    """Compose a fresh application; its server owns one worker-loop lifespan."""
    if dependencies is None:
        dependencies = DIRegistry()
        dependencies.bind(Ledger, provide_ledger)
    # 1. Declare which capabilities this HTTP surface exposes. Bindings are
    #    explicit, including for path parameters (ADR 0026).
    http = Http("public")
    http.get(
        "/orders/{order_id}",
        show_order,
        Binding("order_id", BindingSource.PATH),
        openapi=OpenApiOperation(
            summary="Show an order", publish_description=True, tags=("orders",)
        ),
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
    http.post(
        "/orders/{order_id}/attachments",
        attach,
        Binding("order_id", BindingSource.PATH),
        Binding("session", BindingSource.COOKIE, wire_name="sid"),
        Binding("note", BindingSource.FORM),
        Binding("document", BindingSource.UPLOAD, wire_name="file"),
        openapi=OpenApiOperation(summary="Attach a document", tags=("orders",)),
        max_body_bytes=64 * 1024,
        max_parts=4,
    )

    # 2. Compile this worker's surface against the frozen capability snapshot.
    return http.compile(
        capabilities,
        dependencies=dependencies,
        openapi=OpenApiInfo("Shop API", "2026.1", summary="Orders, over HTTP."),
        openapi_path="/openapi.json",
        request_timeout=5.0,
    )


# ASGI servers drive lifespan themselves. The server-free demonstration uses
# its own fresh application rather than consuming this importable entry point.
asgi = create_application()


@asynccontextmanager
async def lifespan(application: HttpApplication) -> AsyncIterator[None]:
    """A bounded in-memory ASGI host, not a production server implementation."""
    incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    async with asyncio.timeout(5), asyncio.TaskGroup() as owned:
        owned.create_task(application({"type": "lifespan"}, incoming.get, outgoing.put))
        await incoming.put({"type": "lifespan.startup"})
        if (await outgoing.get())["type"] != "lifespan.startup.complete":
            raise RuntimeError("example lifespan startup failed")
        try:
            yield
        finally:
            await incoming.put({"type": "lifespan.shutdown"})
            if (await outgoing.get())["type"] != "lifespan.shutdown.complete":
                raise RuntimeError("example lifespan shutdown failed")


#: The line ending every HTTP message format uses, spelled once.
CRLF = b"\r\n"
BOUNDARY = "xExamplex"


def multipart(*parts: bytes) -> bytes:
    """Assemble a multipart body the way a browser puts one on the wire."""
    delimiter = f"--{BOUNDARY}".encode("ascii")
    joined = b"".join(CRLF + part + CRLF + delimiter for part in parts)
    return delimiter + joined + b"--" + CRLF


def text_part(name: str, value: str) -> bytes:
    head = f'Content-Disposition: form-data; name="{name}"'.encode()
    return head + CRLF + CRLF + value.encode("utf-8")


def file_part(name: str, filename: str, media_type: str, content: bytes) -> bytes:
    head = f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
    return head + CRLF + f"Content-Type: {media_type}".encode() + CRLF + CRLF + content


async def request(
    application: HttpApplication,
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
    await application(scope, receive, send)
    return events[0]["status"], b"".join(event.get("body", b"") for event in events[1:])


async def demonstrate() -> None:
    application = create_application()
    async with lifespan(application):
        print(f"compiled: {application!r}")

        status, payload = await request(application, "GET", "/orders/A-1")
        print(f"read     -> {status} {payload.decode()}")

        status, payload = await request(
            application,
            "PUT",
            "/orders/B-2",
            body=json.dumps({"sku": "gadget", "quantity": 1}).encode("utf-8"),
            headers=((b"content-type", b"application/json"),),
        )
        print(f"write    -> {status} {payload.decode()}")

        # A capability failure is an RFC 9457 problem document, not an exception.
        status, payload = await request(application, "GET", "/orders")
        problem = json.loads(payload)
        print(f"missing  -> {status} {problem['code']}")

        # A cookie, a form field and an upload, in one request (ADR 0072).
        status, payload = await request(
            application,
            "POST",
            "/orders/A-1/attachments",
            body=multipart(
                text_part("note", "Signed copy"),
                file_part("file", "contract.pdf", "application/pdf", b"%PDF-1.7 ..."),
            ),
            headers=(
                (b"content-type", f"multipart/form-data; boundary={BOUNDARY}".encode()),
                (b"cookie", b"sid=session-7; unrelated=x"),
            ),
        )
        print(f"attach   -> {status} {payload.decode()}")

        # An upload beyond the route's limit is a structured 413, never a crash.
        status, payload = await request(
            application,
            "POST",
            "/orders/A-1/attachments",
            body=multipart(
                text_part("note", "Too big"),
                file_part("file", "huge.bin", "application/octet-stream", b"x" * 70_000),
            ),
            headers=(
                (b"content-type", f"multipart/form-data; boundary={BOUNDARY}".encode()),
                (b"cookie", b"sid=session-7"),
            ),
        )
        print(f"oversize -> {status} {json.loads(payload)['code']}")

        status, payload = await request(application, "GET", "/openapi.json")
        document = json.loads(payload)
        print(f"openapi  -> {status} {document['openapi']} paths={sorted(document['paths'])}")

        # The undocumented route is served and absent from the document.
        health_status, _ = await request(application, "GET", "/health")
        print(f"health   -> {health_status} documented={'/health' in document['paths']}")

        # 3. The same surface feeds the protocol-neutral exposure registry, so one
        #    capability exposed over HTTP and MCP has one answer to where it is
        #    reachable (ADR 0070).
        exposures = compile_exposures(capabilities, [application.exposures])
        print(f"exposures-> {[str(identity) for identity in exposures]}")


def main() -> None:
    asyncio.run(demonstrate())


if __name__ == "__main__":
    main()
