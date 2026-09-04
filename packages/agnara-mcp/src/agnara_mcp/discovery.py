"""Official SDK discovery boundary for compiled Agnara MCP tools."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp_types import (
    INVALID_PARAMS,
    DiscoverResult,
    ListToolsResult,
    PaginatedRequestParams,
    RequestParams,
    Tool,
)

from mcp import MCPError

from .protocol import SUPPORTED_MCP_PROTOCOL_VERSIONS
from .tools import McpToolDefinitionError

__all__ = ["build_mcp_discovery_server"]


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise McpToolDefinitionError(f"MCP server {field} must be a non-empty string")
    return value


def _optional_text(value: object, *, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise McpToolDefinitionError(
            f"MCP server {field} must be a string or None, got {type(value).__name__}"
        )
    return value


def _snapshot_tools(tools: Iterable[Tool]) -> tuple[Tool, ...]:
    try:
        iterator = iter(tools)
    except TypeError as error:
        raise McpToolDefinitionError(
            f"MCP discovery tools must be iterable, got {type(tools).__name__}"
        ) from error

    snapshot: list[Tool] = []
    names: set[str] = set()
    for tool in iterator:
        if not isinstance(tool, Tool):
            raise McpToolDefinitionError(
                f"MCP discovery tools must contain Tool values, got {type(tool).__name__}"
            )
        if tool.name in names:
            raise McpToolDefinitionError(f"duplicate MCP discovery tool name {tool.name!r}")
        names.add(tool.name)
        snapshot.append(tool.model_copy(deep=True))
    return tuple(snapshot)


def build_mcp_discovery_server(
    tools: Iterable[Tool],
    *,
    name: str,
    version: str,
    instructions: str | None = None,
) -> Server[Any]:
    """Build a discovery-only official SDK server from a startup tool snapshot.

    The server intentionally serves neither tool invocation nor mutable-list
    notifications. Any cursor is invalid because this first discovery boundary
    returns the complete frozen snapshot in one page.
    """
    server_name = _required_text(name, field="name")
    server_version = _required_text(version, field="version")
    server_instructions = _optional_text(instructions, field="instructions")
    snapshot = _snapshot_tools(tools)

    async def list_tools(
        _ctx: ServerRequestContext[Any],
        params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        cursor = None if params is None else params.cursor
        if cursor is not None:
            raise MCPError(
                code=INVALID_PARAMS,
                message="Invalid tools/list cursor",
                data=cursor,
            )
        return ListToolsResult(
            tools=[tool.model_copy(deep=True) for tool in snapshot],
            ttl_ms=0,
            cache_scope="private",
        )

    server: Server[Any] = Server(
        server_name,
        version=server_version,
        instructions=server_instructions,
        on_list_tools=list_tools,
    )

    async def discover(
        ctx: ServerRequestContext[Any],
        _params: RequestParams | None,
    ) -> DiscoverResult:
        return DiscoverResult(
            supported_versions=list(SUPPORTED_MCP_PROTOCOL_VERSIONS),
            capabilities=server.get_capabilities(protocol_version=ctx.protocol_version),
            instructions=server_instructions,
            ttl_ms=0,
            cache_scope="private",
        )

    server.add_request_handler("server/discover", RequestParams, discover)
    return server
