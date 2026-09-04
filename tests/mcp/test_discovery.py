"""E7.4 official MCP server and tool discovery."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

import pytest
from mcp_types import INVALID_PARAMS, Tool

from agnara import Agnara
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara_mcp import MCP_PROTOCOL_VERSION, Mcp, McpToolDefinitionError, project_mcp_tools
from agnara_mcp import build_mcp_discovery_server as build_server
from mcp import Client, MCPError


def run[T](awaitable: Awaitable[T]) -> T:
    return asyncio.run(awaitable)


def tool(name: str, *, description: str | None = None) -> Tool:
    return Tool(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {}},
    )


def test_discover_advertises_only_the_served_pinned_surface() -> None:
    server = build_server(
        [tool("users.get")],
        name="users",
        version="0.0.0",
        instructions="Use user tools only with an authorized caller.",
    )

    async def inspect() -> None:
        async with Client(server, mode="auto", raise_exceptions=True) as client:
            result = client.session.discover_result
            assert result is not None
            assert result.supported_versions == [MCP_PROTOCOL_VERSION]
            assert result.instructions == "Use user tools only with an authorized caller."
            assert result.ttl_ms == 0
            assert result.cache_scope == "private"
            assert result.meta == {
                "io.modelcontextprotocol/serverInfo": {
                    "name": "users",
                    "version": "0.0.0",
                }
            }
            capabilities = result.capabilities
            assert capabilities.tools is not None
            assert capabilities.tools.list_changed is False
            assert capabilities.resources is None
            assert capabilities.prompts is None
            assert capabilities.tasks is None
            assert capabilities.logging is None
            assert capabilities.completions is None
            assert capabilities.extensions is None
            assert capabilities.experimental is None

    run(inspect())


def test_discovery_serves_the_compiled_capability_projection() -> None:
    app = Agnara("math")

    @app.capability(description="Add two integers")
    def add(left: int, right: int) -> int:
        return left + right

    mcp = Mcp(app)
    mcp.tool(add)
    definition = app.capabilities["math.add"]
    plan = ExecutionPlan.compile(definition, DIRegistry())
    projected = project_mcp_tools(mcp.compile(), [plan])
    server = build_server(projected, name="math", version="1.0.0")

    async def inspect() -> None:
        async with Client(server, mode="auto", raise_exceptions=True) as client:
            result = await client.list_tools(cache_mode="bypass")
            assert result.tools[0].model_dump(by_alias=True, exclude_none=True) == {
                "name": "math.add",
                "description": "Add two integers",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "left": {"type": "integer"},
                        "right": {"type": "integer"},
                    },
                    "required": ["left", "right"],
                    "additionalProperties": False,
                },
            }

    run(inspect())


def test_tools_list_is_ordered_complete_detached_and_private() -> None:
    original = tool("users.first", description="First")
    server = build_server(
        [original, tool("users.second", description="Second")],
        name="users",
        version="0.0.0",
    )
    original.description = "mutated after startup"
    original.input_schema["corrupt"] = True

    async def inspect() -> None:
        async with Client(server, mode="auto", raise_exceptions=True) as client:
            first = await client.list_tools(cache_mode="bypass")
            assert [item.name for item in first.tools] == ["users.first", "users.second"]
            assert first.tools[0].description == "First"
            assert first.tools[0].input_schema == {"type": "object", "properties": {}}
            assert first.ttl_ms == 0
            assert first.cache_scope == "private"
            assert first.next_cursor is None
            assert "nextCursor" not in first.model_dump(by_alias=True, exclude_none=True)

            first.tools[0].description = "mutated response"
            first.tools[0].input_schema["corrupt"] = True
            second = await client.list_tools(cache_mode="bypass")
            assert second.tools[0].description == "First"
            assert second.tools[0].input_schema == {"type": "object", "properties": {}}

    run(inspect())


def test_tools_list_supports_an_empty_snapshot() -> None:
    server = build_server([], name="empty", version="0.0.0")

    async def inspect() -> None:
        async with Client(server, mode="auto", raise_exceptions=True) as client:
            result = await client.list_tools(cache_mode="bypass")
            assert result.tools == []
            assert result.next_cursor is None

    run(inspect())


def test_any_cursor_is_invalid_when_the_complete_snapshot_has_no_pages() -> None:
    server = build_server([tool("users.get")], name="users", version="0.0.0")

    async def inspect() -> None:
        async with Client(server, mode="auto", raise_exceptions=True) as client:
            for cursor in ("not-issued", ""):
                with pytest.raises(MCPError) as captured:
                    await client.list_tools(cursor=cursor, cache_mode="bypass")
                assert captured.value.code == INVALID_PARAMS
                assert captured.value.message == "Invalid tools/list cursor"

    run(inspect())


@pytest.mark.parametrize("field", ["name", "version"])
@pytest.mark.parametrize("value", ["", None, 42])
def test_server_identity_is_validated_at_startup(field: str, value: object) -> None:
    arguments: dict[str, object] = {"name": "users", "version": "0.0.0"}
    arguments[field] = value
    with pytest.raises(McpToolDefinitionError, match=field):
        build_server([], **arguments)  # ty: ignore[invalid-argument-type]


def test_instructions_and_tool_snapshot_are_validated_at_startup() -> None:
    with pytest.raises(McpToolDefinitionError, match="instructions"):
        build_server([], name="users", version="0.0.0", instructions=42)  # ty: ignore[invalid-argument-type]
    with pytest.raises(McpToolDefinitionError, match="iterable"):
        build_server(42, name="users", version="0.0.0")  # ty: ignore[invalid-argument-type]
    with pytest.raises(McpToolDefinitionError, match="Tool values"):
        build_server([object()], name="users", version="0.0.0")  # ty: ignore[invalid-argument-type]
    duplicate = tool("users.get")
    with pytest.raises(McpToolDefinitionError, match="duplicate MCP discovery tool"):
        build_server([duplicate, duplicate], name="users", version="0.0.0")
