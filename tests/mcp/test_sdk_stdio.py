"""Exercise the pinned official SDK over real subprocess pipes."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from importlib.metadata import version
from pathlib import Path

from mcp.client.stdio import StdioServerParameters
from mcp.server.stdio import stdio_server

from agnara import Agnara
from agnara.core.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import ExecutionPlan
from agnara_mcp import MCP_PROTOCOL_VERSION, Mcp, build_mcp_server
from mcp import Client


class Resource:
    pass


async def serve(shutdown_log: Path) -> None:
    app = Agnara("stdio")
    registry = DIRegistry()
    entered = asyncio.Event()
    unwound = asyncio.Event()
    events: list[str] = []

    @provider(scope=Scope.SINGLETON)
    async def resource() -> AsyncIterator[Resource]:
        events.append("resource.open")
        try:
            yield Resource()
        finally:
            events.append("resource.close")

    registry.bind(Resource, resource)

    @app.capability
    async def echo(value: int, resource: Resource) -> int:
        return value

    @app.capability(scopes={"write"})
    async def restricted() -> str:
        events.append("restricted.effect")
        return "private"

    @app.capability
    async def blocked(resource: Resource) -> str:
        entered.set()
        try:
            await asyncio.Future()
        finally:
            events.append("blocked.unwound")
            unwound.set()
        return "unexpected"

    @app.capability
    async def wait_for(stage: str) -> str:
        await {"entered": entered, "unwound": unwound}[stage].wait()
        return stage

    mcp = Mcp(app)
    mcp.tool(echo)
    mcp.tool(restricted)
    mcp.tool(blocked)
    mcp.tool(wait_for)
    container = DIContainer(registry)
    server = build_mcp_server(
        mcp.compile(),
        [ExecutionPlan.compile(app.capabilities[key], registry) for key in app.capabilities],
        container,
        name="agnara-stdio-test",
        version="test",
    )
    try:
        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, server.create_initialization_options())
        events.append("transport.closed")
    finally:
        await container.aclose()
        shutdown_log.write_text("\n".join(events), encoding="utf-8")


def test_host_owned_stdio_negotiation_invocation_cancellation_and_shutdown(tmp_path: Path) -> None:
    assert version("mcp") == version("mcp-types") == "2.2.0"
    shutdown_log = tmp_path / "shutdown.txt"
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "tests.mcp.test_sdk_stdio", str(shutdown_log)]
    )

    async def scenario() -> None:
        async with asyncio.timeout(15), Client(params, mode="auto") as client:
            assert client.protocol_version == MCP_PROTOCOL_VERSION == "2026-07-28"
            assert client.session.discover_result is not None
            listed = await client.list_tools()
            assert "stdio.echo" in {tool.name for tool in listed.tools}
            result = await client.call_tool("stdio.echo", {"value": 42})
            assert result.structured_content == {"result": 42}
            denied = await client.call_tool("stdio.restricted", {})
            assert denied.is_error
            async with asyncio.TaskGroup() as group:
                pending = group.create_task(client.call_tool("stdio.blocked", {}))
                entered = await client.call_tool("stdio.wait_for", {"stage": "entered"})
                assert entered.structured_content == {"result": "entered"}
                pending.cancel()
                await asyncio.wait({pending})
                assert pending.cancelled()
                unwound = await client.call_tool("stdio.wait_for", {"stage": "unwound"})
                assert unwound.structured_content == {"result": "unwound"}
            assert not shutdown_log.exists()

    asyncio.run(scenario())
    assert shutdown_log.read_text(encoding="utf-8").splitlines() == [
        "resource.open",
        "blocked.unwound",
        "transport.closed",
        "resource.close",
    ]


if __name__ == "__main__":
    asyncio.run(serve(Path(sys.argv[1])))
