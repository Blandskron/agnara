"""Official SDK discovery boundary for compiled Agnara MCP tools."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp_types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    DiscoverResult,
    InputRequiredResult,
    ListToolsResult,
    PaginatedRequestParams,
    RequestParams,
    Tool,
)

from mcp import MCPError

from .authorization import McpAuthorization
from .protocol import SUPPORTED_MCP_PROTOCOL_VERSIONS
from .tools import McpToolDefinitionError

__all__ = ["build_mcp_discovery_server"]

type _CallToolHandler = Callable[
    [ServerRequestContext[Any], CallToolRequestParams],
    Awaitable[CallToolResult | InputRequiredResult],
]


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
    authorization: McpAuthorization | None = None,
) -> Server[Any]:
    """Build a discovery-only official SDK server from a startup tool snapshot.

    The server intentionally serves neither tool invocation nor mutable-list
    notifications. Any cursor is invalid because this first discovery boundary
    returns the complete frozen snapshot in one page.

    Use ``build_mcp_server`` when the same snapshot must also serve
    ``tools/call``.
    """
    return _build_server(
        tools,
        name=name,
        version=version,
        instructions=instructions,
        authorization=authorization,
        on_call_tool=None,
    )


def _build_server(
    tools: Iterable[Tool],
    *,
    name: str,
    version: str,
    instructions: str | None,
    authorization: McpAuthorization | None,
    on_call_tool: _CallToolHandler | None,
) -> Server[Any]:
    """Assemble the shared discovery surface, optionally serving invocation.

    Advertised capabilities follow the handlers actually registered, so a
    server without ``on_call_tool`` never claims a tool-invocation surface it
    would answer with ``METHOD_NOT_FOUND``.
    """
    server_name = _required_text(name, field="name")
    server_version = _required_text(version, field="version")
    server_instructions = _optional_text(instructions, field="instructions")
    snapshot = _snapshot_tools(tools)
    if authorization is not None:
        if not isinstance(authorization, McpAuthorization):
            raise TypeError(
                "authorization must be McpAuthorization or None, got "
                f"{type(authorization).__name__}"
            )
        authorization._validate_tools(snapshot)

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
        visible_names = None if authorization is None else authorization.discoverable_tool_names()
        return ListToolsResult(
            tools=[
                tool.model_copy(deep=True)
                for tool in snapshot
                if visible_names is None or tool.name in visible_names
            ],
            ttl_ms=0,
            cache_scope="private",
        )

    server: Server[Any] = Server(
        server_name,
        version=server_version,
        instructions=server_instructions,
        on_list_tools=list_tools,
        on_call_tool=on_call_tool,
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
