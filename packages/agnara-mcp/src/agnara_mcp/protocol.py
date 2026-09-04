"""Pinned Model Context Protocol revision and SDK baseline."""

from __future__ import annotations

from typing import Final

__all__ = [
    "MCP_PROTOCOL_VERSION",
    "MCP_PYTHON_SDK_VERSION",
    "SUPPORTED_MCP_PROTOCOL_VERSIONS",
]


MCP_PROTOCOL_VERSION: Final = "2026-07-28"
"""The protocol revision targeted by Agnara's first MCP adapter line."""

SUPPORTED_MCP_PROTOCOL_VERSIONS: Final = (MCP_PROTOCOL_VERSION,)
"""Protocol revisions for which Agnara intends to maintain conformance tests."""

MCP_PYTHON_SDK_VERSION: Final = "2.1.1"
"""The exact official Python SDK version used at the adapter boundary."""
