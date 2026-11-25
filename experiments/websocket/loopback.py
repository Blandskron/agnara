"""Minimal stdlib RFC 6455 TCP loopback harness for WS-01 (no external deps)."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import struct
from collections.abc import Awaitable, Callable
from typing import Any

_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

type _ASGIApp = Callable[
    [
        dict[str, Any],
        Callable[[], Awaitable[dict[str, Any]]],
        Callable[[dict[str, Any]], Awaitable[None]],
    ],
    Awaitable[None],
]


def _ws_accept_key(client_key: str) -> str:
    digest = hashlib.sha1(client_key.strip().encode("ascii") + _WS_GUID).digest()
    return base64.b64encode(digest).decode("ascii")


def _encode_frame(opcode: int, payload: bytes, *, mask: bool) -> bytes:
    header = bytearray([0x80 | opcode])
    length = len(payload)
    mask_bit = 0x80 if mask else 0x00
    if length < 126:
        header.append(mask_bit | length)
    elif length < 65_536:
        header.append(mask_bit | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(mask_bit | 127)
        header.extend(struct.pack("!Q", length))
    if not mask:
        return bytes(header) + payload
    key = os.urandom(4)
    masked = bytes(byte ^ key[idx % 4] for idx, byte in enumerate(payload))
    return bytes(header) + key + masked


async def _read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    first_two = await reader.readexactly(2)
    b1, b2 = first_two[0], first_two[1]
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        (length,) = struct.unpack("!H", await reader.readexactly(2))
    elif length == 127:
        (length,) = struct.unpack("!Q", await reader.readexactly(8))
    mask_key = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(length)
    if masked:
        payload = bytes(byte ^ mask_key[idx % 4] for idx, byte in enumerate(payload))
    return opcode, payload


async def _read_http_block(
    reader: asyncio.StreamReader,
) -> tuple[str, dict[str, str], list[tuple[bytes, bytes]]]:
    raw = await reader.readuntil(b"\r\n\r\n")
    lines = raw[:-4].decode("latin-1").split("\r\n")
    request_line = lines[0]
    header_map: dict[str, str] = {}
    raw_headers: list[tuple[bytes, bytes]] = []
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, val = line.split(":", 1)
        clean_name = name.strip().lower()
        clean_val = val.strip()
        header_map[clean_name] = clean_val
        raw_headers.append((clean_name.encode("latin-1"), clean_val.encode("latin-1")))
    return request_line, header_map, raw_headers


class LoopbackWebSocketServer:
    """Minimal asyncio TCP server driving one ASGI ``websocket`` callable."""

    def __init__(self, app: _ASGIApp) -> None:
        self._app = app
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.port: int = 0

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._spawn_client, "127.0.0.1", 0)
        sock = self._server.sockets[0]
        self.port = int(sock.getsockname()[1])
        return self.port

    def _spawn_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(self._handle_connection(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        receive_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        accepted = asyncio.Event()
        closed_by_app = False
        pump_task: asyncio.Task[None] | None = None
        try:
            request_line, header_map, raw_headers = await _read_http_block(reader)
            parts = request_line.split(" ")
            target = parts[1] if len(parts) >= 2 else "/"
            path, _, query = target.partition("?")
            scope: dict[str, Any] = {
                "type": "websocket",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "scheme": "ws",
                "path": path,
                "raw_path": path.encode("latin-1"),
                "query_string": query.encode("latin-1"),
                "root_path": "",
                "headers": raw_headers,
                "server": ("127.0.0.1", self.port),
            }
            ws_key = header_map.get("sec-websocket-key", "")
            await receive_queue.put({"type": "websocket.connect"})

            async def reader_loop() -> None:
                await accepted.wait()
                try:
                    while True:
                        opcode, payload = await _read_frame(reader)
                        if opcode == 0x8:
                            code = (
                                struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else 1000
                            )
                            await receive_queue.put({"type": "websocket.disconnect", "code": code})
                            return
                        if opcode == 0x9:
                            writer.write(_encode_frame(0xA, payload, mask=False))
                            await writer.drain()
                        elif opcode == 0x1:
                            await receive_queue.put(
                                {"type": "websocket.receive", "text": payload.decode("utf-8")}
                            )
                except asyncio.IncompleteReadError, ConnectionError, OSError:
                    await receive_queue.put({"type": "websocket.disconnect", "code": 1006})

            async def receive() -> dict[str, Any]:
                return await receive_queue.get()

            async def send(message: dict[str, Any]) -> None:
                nonlocal closed_by_app
                msg_type = message["type"]
                if msg_type == "websocket.accept":
                    response = (
                        "HTTP/1.1 101 Switching Protocols\r\n"
                        "Upgrade: websocket\r\n"
                        "Connection: Upgrade\r\n"
                        f"Sec-WebSocket-Accept: {_ws_accept_key(ws_key)}\r\n\r\n"
                    ).encode("ascii")
                    writer.write(response)
                    await writer.drain()
                    accepted.set()
                    return
                if msg_type == "websocket.send":
                    text = message.get("text")
                    if isinstance(text, str):
                        writer.write(_encode_frame(0x1, text.encode("utf-8"), mask=False))
                        await writer.drain()
                    return
                if msg_type == "websocket.close":
                    closed_by_app = True
                    if not accepted.is_set():
                        writer.write(
                            b"HTTP/1.1 403 Forbidden\r\n"
                            b"Content-Length: 0\r\n"
                            b"Connection: close\r\n\r\n"
                        )
                        await writer.drain()
                    else:
                        code = int(message.get("code", 1000))
                        reason = str(message.get("reason", "")).encode("utf-8")[:123]
                        writer.write(
                            _encode_frame(0x8, struct.pack("!H", code) + reason, mask=False)
                        )
                        await writer.drain()
                    writer.close()

            pump_task = asyncio.create_task(reader_loop())
            await self._app(scope, receive, send)
        except Exception:
            if not closed_by_app:
                with contextlib.suppress(OSError):
                    writer.close()
        finally:
            if pump_task is not None:
                pump_task.cancel()
                with contextlib.suppress(BaseException):
                    await pump_task
            if not writer.is_closing():
                writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    async def aclose(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


class LoopbackWebSocketClient:
    """Minimal stdlib RFC 6455 client for testing pre-upgrade and live streams."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer

    @classmethod
    async def open(
        cls,
        port: int,
        path: str = "/ws",
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, LoopbackWebSocketClient | None]:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req_headers = {
            "Host": f"127.0.0.1:{port}",
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Key": key,
            "Sec-WebSocket-Version": "13",
        }
        if headers:
            req_headers.update(headers)
        lines = [f"GET {path} HTTP/1.1"]
        lines.extend(f"{k}: {v}" for k, v in req_headers.items())
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
        await writer.drain()

        status_line, resp_headers, _ = await _read_http_block(reader)
        status = int(status_line.split(" ", 2)[1])
        if status != 101:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            return status, None
        expected_accept = _ws_accept_key(key)
        if resp_headers.get("sec-websocket-accept") != expected_accept:
            raise AssertionError("Sec-WebSocket-Accept mismatch")
        return status, cls(reader, writer)

    async def send_text(self, text: str) -> None:
        self._writer.write(_encode_frame(0x1, text.encode("utf-8"), mask=True))
        await self._writer.drain()

    async def recv_event(self) -> tuple[str, Any]:
        opcode, payload = await _read_frame(self._reader)
        if opcode == 0x1:
            return ("text", json.loads(payload.decode("utf-8")))
        if opcode == 0x8:
            code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else 1000
            return ("close", code)
        return (f"opcode:{opcode}", payload)

    async def abort_tcp(self) -> None:
        self._writer.close()
        with contextlib.suppress(OSError):
            await self._writer.wait_closed()
