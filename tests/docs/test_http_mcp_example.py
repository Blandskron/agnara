"""A shared capability runs directly and through both adapters without leaked tasks."""

import asyncio
import subprocess
import sys
from pathlib import Path

from tests.reference_apps.http_mcp_guide import verify_guide

SOURCE = Path(__file__).resolve().parents[2] / "examples/http_mcp.py"


def test_shared_capability_validates_all_entry_points_and_closes_tasks() -> None:
    asyncio.run(verify_guide(SOURCE))


def test_shared_example_runs_outside_checkout(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SOURCE)], cwd=tmp_path, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    assert "Direct: Success(value=5)" in result.stdout
    assert "HTTP: (200, 5)" in result.stdout
