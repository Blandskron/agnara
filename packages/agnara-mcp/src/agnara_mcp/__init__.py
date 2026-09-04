"""Model Context Protocol exposure adapter for Agnara capabilities.

Owns MCP server projection, tool discovery, schema mapping, MCP
authorization integration and MCP-specific error representations.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` sections 3 and 4, and EPIC 7 in ``BACKLOG.md``.
"""

from .authorization import (
    McpAuthenticatedIdentity,
    McpAuthorization,
    McpAuthorizationDefinitionError,
    McpPrincipalMapper,
)
from .discovery import build_mcp_discovery_server
from .interaction import McpInteractionProjectionError, project_mcp_interaction_required
from .protocol import (
    MCP_PROTOCOL_VERSION,
    MCP_PYTHON_SDK_VERSION,
    SUPPORTED_MCP_PROTOCOL_VERSIONS,
)
from .schema import project_mcp_tools
from .tools import FrozenMcpTools, Mcp, McpToolDefinitionError, McpToolExposure

__all__ = [
    "MCP_PROTOCOL_VERSION",
    "MCP_PYTHON_SDK_VERSION",
    "SUPPORTED_MCP_PROTOCOL_VERSIONS",
    "FrozenMcpTools",
    "Mcp",
    "McpAuthenticatedIdentity",
    "McpAuthorization",
    "McpAuthorizationDefinitionError",
    "McpInteractionProjectionError",
    "McpPrincipalMapper",
    "McpToolDefinitionError",
    "McpToolExposure",
    "build_mcp_discovery_server",
    "project_mcp_interaction_required",
    "project_mcp_tools",
]
