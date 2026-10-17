"""Validate the exact copied MCP guide against installed artifacts under Python -I."""

from __future__ import annotations

import asyncio
import json
import runpy
import sys
from pathlib import Path
from typing import Any

from mcp_types import INVALID_PARAMS, CallToolResult, TextContent

from agnara_mcp import MCP_PROTOCOL_VERSION


def document(result: CallToolResult) -> dict[str, Any]:
    assert len(result.content) == 1 and isinstance(result.content[0], TextContent)
    decoded = json.loads(result.content[0].text)
    assert isinstance(decoded, dict)
    return decoded


def validate(outcome: dict[str, Any]) -> None:
    """Check SDK objects and effects before emitting the artifact success marker."""
    assert outcome["protocol"] == MCP_PROTOCOL_VERSION
    listing = outcome["listing"]
    assert [tool.name for tool in listing.tools] == ["catalog.total", "catalog.broken"]
    assert listing.ttl_ms == 0 and listing.cache_scope == "private"
    assert listing.next_cursor is None
    assert listing.tools[0].input_schema == {
        "type": "object",
        "properties": {
            "quantity": {"type": "integer"},
            "unit_price": {"type": "integer"},
        },
        "required": ["quantity"],
        "additionalProperties": False,
    }
    assert all(tool.output_schema is None for tool in listing.tools)
    assert outcome["unknown_code"] == INVALID_PARAMS
    assert outcome["rejected_effects"] == []
    results = outcome["results"]
    assert set(results) == {
        "valid",
        "recovered",
        "invalid_input",
        "forged_dependency",
        "denied",
        "handler_failure",
    }
    for name, expected in (("valid", 30), ("recovered", 10)):
        result = results[name]
        assert result.is_error is False
        assert result.structured_content == document(result) == {"result": expected}
    for name, code in (
        ("invalid_input", "invalid_input"),
        ("forged_dependency", "invalid_input"),
        ("denied", "forbidden"),
        ("handler_failure", "internal_failure"),
    ):
        result = results[name]
        assert result.is_error is True and document(result)["code"] == code
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


async def run_guide(path: Path) -> dict[str, Any]:
    # run_path loads only this exact local source. Its __main__ printer does not
    # run; the guide's own demonstration creates and drives the official client.
    namespace = runpy.run_path(str(path))
    async with asyncio.timeout(20):
        outcome = await namespace["demonstrate"]()
    assert asyncio.all_tasks() == {asyncio.current_task()}, "MCP connection tasks survived"
    return outcome


if __name__ == "__main__":
    validate(asyncio.run(run_guide(Path(sys.argv[1]))))
    print("MCP_GUIDE_ARTIFACT_OK")
