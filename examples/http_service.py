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


@app.capability(description="Attach a note and a document to one order.")
def attach(order_id: str, session: str, note: str, document: bytes) -> dict[str, Any]:
    """A cookie, a form field and an upload: the 0.1.0a4 request surface."""
    return {
        "order_id": order_id,
        "session": session,
        "note": note,
        # The client filename is never exposed (ADR 0072), so an application
        # names its own artefacts. Here that means reporting a size.
        "bytes": len(document),
    }


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

    # A cookie, a form field and an upload, in one request (ADR 0072).
    status, payload = request(
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
    status, payload = request(
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
