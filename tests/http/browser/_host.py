"""A tiny HTTP bridge that drives Agnara's ASGI surface dispatcher in tests."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

from agnara_http._dispatch import _CompiledExposure
from agnara_http._documentation import (
    _documentation_security_headers,
    _DocumentationPage,
    _DocumentationRequest,
)
from agnara_http._routing import _RouteRegistry
from agnara_http._surfaces import _compile_surfaces, _HTTPSurface, _SurfaceDispatcher

type _Message = dict[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]
type _Send = Callable[[_Message], Awaitable[None]]
type _ASGIApp = Callable[[dict[str, Any], _Receive, _Send], Awaitable[None]]


async def _not_found(_scope: dict[str, Any], _receive: _Receive, send: _Send) -> None:
    body = b"not found"
    await send(
        {
            "type": "http.response.start",
            "status": 404,
            "headers": (
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ),
        }
    )
    await send({"type": "http.response.body", "body": body})


def documentation_app(
    page: _DocumentationPage,
    request: _DocumentationRequest,
    document: bytes,
) -> _ASGIApp:
    """Compile one provider page, its assets and optional schema route."""
    surfaces = [
        _HTTPSurface(
            "documentation.page",
            "/docs",
            "text/html; charset=utf-8",
            page.html,
            _documentation_security_headers(page.csp),
        )
    ]
    asset_root = request.assets_url.rstrip("/")
    for index, (name, asset) in enumerate(page.assets.items()):
        path = f"/{name}" if not asset_root else f"{asset_root}/{name}"
        surfaces.append(
            _HTTPSurface(
                f"documentation.asset.{index}",
                path,
                asset.media_type,
                asset.body,
                ((b"cache-control", b"no-store"),),
            )
        )
    if request.document_url is not None:
        surfaces.append(
            _HTTPSurface(
                "documentation.schema",
                request.document_url,
                "application/json",
                document,
                ((b"cache-control", b"no-store"),),
            )
        )

    routes = _compile_surfaces(
        surfaces,
        _RouteRegistry[_CompiledExposure]().freeze(),
    )
    return _SurfaceDispatcher(routes, _not_found)


def empty_app() -> _ASGIApp:
    """Return a dispatcher with no published documentation route."""
    routes = _compile_surfaces((), _RouteRegistry[_CompiledExposure]().freeze())
    return _SurfaceDispatcher(routes, _not_found)


class DocumentationHost:
    """Serve an ASGI app on an ephemeral loopback port for Playwright."""

    def __init__(self, app: _ASGIApp) -> None:
        self._app = app
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Self:
        app = self._app

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                split = urlsplit(self.path)
                messages: list[_Message] = []

                async def receive() -> _Message:
                    return {"type": "http.request", "body": b"", "more_body": False}

                async def send(message: _Message) -> None:
                    messages.append(message)

                scope = {
                    "type": "http",
                    "method": "GET",
                    "path": split.path,
                    "raw_path": split.path.encode("ascii"),
                    "query_string": split.query.encode("ascii"),
                }
                asyncio.run(app(scope, receive, send))
                start = next(item for item in messages if item["type"] == "http.response.start")
                body = b"".join(
                    item.get("body", b"")
                    for item in messages
                    if item["type"] == "http.response.body"
                )
                self.send_response(start["status"])
                for name, value in start.get("headers", ()):
                    self.send_header(name.decode("ascii"), value.decode("ascii"))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    @property
    def origin(self) -> str:
        if self._server is None:
            raise RuntimeError("documentation host has not been started")
        host = str(self._server.server_address[0])
        port = int(self._server.server_address[1])
        return f"http://{host}:{port}"

    def url(self, path: str) -> str:
        return f"{self.origin}{path}"


def header_map(response_headers: Mapping[str, str]) -> dict[str, str]:
    """Normalize Playwright's case-insensitive header mapping for assertions."""
    return {name.lower(): value for name, value in response_headers.items()}
