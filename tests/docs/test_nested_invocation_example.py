"""Executable learning example: parent authorization never authorizes a child."""

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from examples.nested_invocation import demonstrate

from agnara import Principal
from agnara.execution import Failure, FailureCode, Success


@pytest.mark.parametrize(
    ("scopes", "expected", "handlers"),
    [
        ({"summary:read", "catalog:read"}, Success("Summary: A-1: widget"), ["summary", "product"]),
        ({"summary:read"}, Success("Product unavailable: forbidden"), ["summary"]),
        ({"catalog:read"}, Failure(FailureCode.FORBIDDEN, "required scopes not granted"), []),
    ],
)
def test_nested_example_checks_each_capability(scopes, expected, handlers) -> None:
    outcome, calls = asyncio.run(demonstrate(Principal("reader", scopes=scopes)))
    assert outcome == expected
    assert calls == handlers


def test_example_entry_point_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "nested_invocation.py"
    result = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "authorized: Summary: A-1: widget; handlers=['summary', 'product']",
        "child denied: Product unavailable: forbidden; handlers=['summary']",
        "parent denied: forbidden; handlers=[]",
    ]
