"""Shared capability contract crosses both adapter boundaries without leaked tasks."""

import asyncio
import subprocess
import sys
from pathlib import Path

from examples.http_mcp import demonstrate
from examples.mcp_tools import text_document


def test_shared_capability_validates_both_transports_and_closes_tasks() -> None:
    async def run():
        result = await demonstrate()
        assert asyncio.all_tasks() == {asyncio.current_task()}
        return result

    result = asyncio.run(run())
    assert result["http_ok"] == (200, 5)
    assert result["http_bad"][0] == 400
    assert [tool.name for tool in result["tools"].tools] == ["calculator.add"]
    assert text_document(result["mcp_ok"])["result"] == 5
    assert text_document(result["mcp_bad"])["code"] == "invalid_input"
    assert result["calls"] == [(2, 3), (2, 3)]


def test_shared_example_runs_outside_checkout(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "examples/http_mcp.py"
    result = subprocess.run(
        [sys.executable, str(source)], cwd=tmp_path, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    assert "HTTP: (200, 5)" in result.stdout
