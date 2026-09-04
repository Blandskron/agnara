"""E7.1 protocol and official SDK pinning contract."""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

import mcp_types

from agnara_mcp import (
    MCP_PROTOCOL_VERSION,
    MCP_PYTHON_SDK_VERSION,
    SUPPORTED_MCP_PROTOCOL_VERSIONS,
)

ROOT = Path(__file__).resolve().parents[2]


def test_mcp_protocol_contract_targets_one_exact_revision() -> None:
    assert MCP_PROTOCOL_VERSION == "2026-07-28"
    assert SUPPORTED_MCP_PROTOCOL_VERSIONS == (MCP_PROTOCOL_VERSION,)
    assert isinstance(SUPPORTED_MCP_PROTOCOL_VERSIONS, tuple)


def test_mcp_protocol_contract_matches_the_pinned_official_sdk() -> None:
    assert MCP_PYTHON_SDK_VERSION == "2.1.1"
    assert importlib.metadata.version("mcp") == MCP_PYTHON_SDK_VERSION
    assert mcp_types.LATEST_PROTOCOL_VERSION == MCP_PROTOCOL_VERSION


def test_only_the_mcp_adapter_declares_the_official_sdk() -> None:
    package_files = sorted((ROOT / "packages").glob("*/pyproject.toml"))
    declared_by: dict[str, list[str]] = {}
    for path in package_files:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        dependencies = document["project"].get("dependencies", [])
        matches = [dependency for dependency in dependencies if dependency.startswith("mcp")]
        if matches:
            declared_by[path.parent.name] = matches

    assert declared_by == {"agnara-mcp": [f"mcp=={MCP_PYTHON_SDK_VERSION}"]}
