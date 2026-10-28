"""Invoke one capability through HTTP and the official in-process MCP client.

Run with ``uv run python examples/http_mcp.py``. Compatible with published
1.0.3. No server, authentication provider or network endpoint is deployed.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry
from agnara.execution import ExecutionPlan
from agnara_http import Binding, BindingSource, Http
from agnara_mcp import Mcp, McpAuthenticatedIdentity, McpAuthorization, build_mcp_server
from mcp import Client


def reject_authenticated(identity: McpAuthenticatedIdentity) -> Principal:
    raise ValueError("this anonymous fixture has no trusted authenticated mapping")


async def demonstrate() -> dict[str, Any]:
    app = Agnara("calculator")
    calls: list[tuple[int, int]] = []

    @app.capability(output=int)
    def add(a: int, b: int) -> int:
        calls.append((a, b))
        return a + b

    http = Http("public")
    http.get("/add", add, Binding("a", BindingSource.QUERY), Binding("b", BindingSource.QUERY))
    mcp = Mcp(app, surface="agents")
    mcp.tool(add)
    capabilities = app.compile()
    dependencies = DIRegistry()
    asgi = http.compile(capabilities, dependencies=dependencies)

    # The ASGI host owns its HTTP container through the compiled lifespan.
    # The in-process MCP host owns a separate container on this same loop.
    @asynccontextmanager
    async def http_lifespan():
        incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with asyncio.TaskGroup() as group:
            group.create_task(asgi({"type": "lifespan"}, incoming.get, outgoing.put))
            await incoming.put({"type": "lifespan.startup"})
            assert (await outgoing.get())["type"] == "lifespan.startup.complete"
            try:
                yield
            finally:
                await incoming.put({"type": "lifespan.shutdown"})
                assert (await outgoing.get())["type"] == "lifespan.shutdown.complete"

    async def request(query: bytes) -> tuple[int, Any]:
        messages: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)

        await asgi(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/add",
                "raw_path": b"/add",
                "query_string": query,
                "headers": [],
                "server": ("fixture", 80),
                "client": ("fixture", 1),
                "root_path": "",
            },
            receive,
            send,
        )
        return messages[0]["status"], json.loads(b"".join(m.get("body", b"") for m in messages))

    container = DIContainer(dependencies)
    try:
        exposures = mcp.compile()
        server = build_mcp_server(
            exposures,
            [ExecutionPlan.compile(item, dependencies) for item in capabilities.values()],
            container,
            name="shared-capability-example",
            version="1.0.3",
            authorization=McpAuthorization(exposures, reject_authenticated),
            timeout=2,
        )
        async with asyncio.timeout(10), http_lifespan(), Client(server, mode="auto") as client:
            http_ok = await request(b"a=2&b=3")
            http_bad = await request(b"a=bad&b=3")
            tools = await client.list_tools()
            mcp_ok = await client.call_tool("calculator.add", {"a": 2, "b": 3})
            mcp_bad = await client.call_tool("calculator.add", {"a": "bad", "b": 3})
            return {
                "http_ok": http_ok,
                "http_bad": http_bad,
                "tools": tools,
                "mcp_ok": mcp_ok,
                "mcp_bad": mcp_bad,
                "calls": calls,
            }
    finally:
        await container.aclose()


if __name__ == "__main__":
    result = asyncio.run(demonstrate())
    print(f"HTTP: {result['http_ok']}; MCP: {result['mcp_ok']}")
