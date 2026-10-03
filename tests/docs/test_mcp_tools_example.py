"""The runnable MCP tutorial drives the official client and owns its resources."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from examples.mcp_tools import demonstrate, reject_authenticated, text_document
from mcp_types import INVALID_PARAMS

from agnara_mcp import MCP_PROTOCOL_VERSION, McpAuthenticatedIdentity


def test_mcp_tools_example_discovery_invocation_and_cleanup() -> None:
    async def run():
        outcome = await demonstrate()
        assert asyncio.all_tasks() == {asyncio.current_task()}
        return outcome

    outcome = asyncio.run(run())
    assert outcome["protocol"] == MCP_PROTOCOL_VERSION
    listing = outcome["listing"]
    assert [tool.name for tool in listing.tools] == ["catalog.total", "catalog.broken"]
    assert listing.ttl_ms == 0 and listing.cache_scope == "private"
    assert listing.next_cursor is None
    total = listing.tools[0]
    assert total.input_schema == {
        "type": "object",
        "properties": {
            "quantity": {"type": "integer"},
            "unit_price": {"type": "integer"},
        },
        "required": ["quantity"],
        "additionalProperties": False,
    }
    assert total.output_schema is None
    assert outcome["rejected_effects"] == []
    assert outcome["unknown_code"] == INVALID_PARAMS
    results = outcome["results"]
    for name, expected in (("valid", 30), ("recovered", 10)):
        result = results[name]
        assert result.is_error is False
        assert result.structured_content == text_document(result) == {"result": expected}
    for name, code in (
        ("invalid_input", "invalid_input"),
        ("forged_dependency", "invalid_input"),
        ("denied", "forbidden"),
        ("handler_failure", "internal_failure"),
    ):
        result = results[name]
        assert result.is_error is True and text_document(result)["code"] == code
        assert "demo-private-diagnostic" not in result.model_dump_json()
    assert outcome["effects"] == [
        "resource.open",
        "total:3:10",
        "resource.close",
        "resource.open",
        "broken.handler",
        "resource.close",
        "resource.open",
        "total:1:10",
        "resource.close",
    ]


def test_anonymous_tutorial_never_accepts_an_authenticated_identity() -> None:
    identity = McpAuthenticatedIdentity("client", None, None, None, frozenset({"catalog:read"}))
    with pytest.raises(ValueError, match="not configured"):
        reject_authenticated(identity)


def test_mcp_tools_example_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "mcp_tools.py"
    completed = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "protocol: 2026-07-28",
        "tools: ['catalog.total', 'catalog.broken']",
        "valid: 30",
        "invalid_input: invalid_input",
        "forged_dependency: invalid_input",
        "denied: forbidden",
        "handler_failure: internal_failure",
        "unknown_tool: protocol_error (-32602)",
        "recovered: 10",
        "effects: ['resource.open', 'total:3:10', 'resource.close', 'resource.open', "
        "'broken.handler', 'resource.close', 'resource.open', 'total:1:10', 'resource.close']",
    ]
