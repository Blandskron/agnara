"""Model Context Protocol exposure adapter for Agnara capabilities.

Owns MCP server projection, tool discovery, schema mapping, MCP
authorization integration and MCP-specific error representations.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` sections 3 and 4, and EPIC 7 in ``BACKLOG.md``.
"""

from .protocol import (
    MCP_PROTOCOL_VERSION,
    MCP_PYTHON_SDK_VERSION,
    SUPPORTED_MCP_PROTOCOL_VERSIONS,
)
from .tools import FrozenMcpTools, Mcp, McpToolDefinitionError, McpToolExposure

__all__ = [
    "MCP_PROTOCOL_VERSION",
    "MCP_PYTHON_SDK_VERSION",
    "SUPPORTED_MCP_PROTOCOL_VERSIONS",
    "FrozenMcpTools",
    "Mcp",
    "McpToolDefinitionError",
    "McpToolExposure",
]
