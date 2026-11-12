"""Validate the shared capability example using only installed packages."""

from __future__ import annotations

import asyncio
import json
import runpy
import sys
from pathlib import Path

from mcp_types import TextContent

from agnara.execution import Failure, FailureCode, Success


async def verify_guide(path: Path) -> None:
    demonstrate = runpy.run_path(str(path))["demonstrate"]
    result = await demonstrate()

    assert result["direct_ok"] == Success(5)
    direct_failure = result["direct_bad"]
    assert isinstance(direct_failure, Failure) and direct_failure.code is FailureCode.INVALID_INPUT
    assert result["http_ok"] == (200, 5)
    assert result["http_bad"][0] == 400
    assert [tool.name for tool in result["tools"].tools] == ["calculator.add"]
    for key, is_error, field, expected in (
        ("mcp_ok", False, "result", 5),
        ("mcp_bad", True, "code", "invalid_input"),
    ):
        outcome = result[key]
        assert outcome.is_error is is_error
        assert len(outcome.content) == 1 and isinstance(outcome.content[0], TextContent)
        assert json.loads(outcome.content[0].text)[field] == expected

    assert result["calls"] == [(2, 3), (2, 3), (2, 3)]
    assert asyncio.all_tasks() == {asyncio.current_task()}, "host tasks survived shutdown"


if __name__ == "__main__":
    asyncio.run(verify_guide(Path(sys.argv[1])))
    print("HTTP_MCP_GUIDE_ARTIFACT_OK")
