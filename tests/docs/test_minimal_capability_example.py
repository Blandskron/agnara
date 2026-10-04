"""Minimal direct execution is a pasteable working program."""

import asyncio
import subprocess
import sys
from pathlib import Path

from examples.minimal_capability import demonstrate

from agnara.execution import Success


def test_minimal_result() -> None:
    assert asyncio.run(demonstrate()) == Success(5)


def test_minimal_runs_outside_checkout(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "examples/minimal_capability.py"
    result = subprocess.run(
        [sys.executable, str(source)], cwd=tmp_path, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert "5" in result.stdout
