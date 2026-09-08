"""Regression coverage for names that make generated source exceed Ruff's limit."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agnara_cli import EXIT_OK, main

PROJECT = "enterprise_commerce_platform"
APP = "payment_reconciliation_service"


def _generate(directory: Path) -> Path:
    assert main(["project", "create", PROJECT, "--directory", str(directory)]) == EXIT_OK
    project = directory / PROJECT
    assert main(["app", "create", APP, "--project", str(project)]) == EXIT_OK
    return project


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.mark.parametrize("command", [("check",), ("format", "--check")])
def test_long_names_generate_ruff_clean_source(tmp_path: Path, command: tuple[str, ...]) -> None:
    try:
        from ruff.__main__ import find_ruff_bin
    except ImportError:  # pragma: no cover - ruff is a development pin
        pytest.skip("ruff is not installed")

    project = _generate(tmp_path)
    completed = subprocess.run(
        [str(find_ruff_bin()), *command, "."],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_long_names_generate_byte_identical_trees(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    assert _tree(_generate(first)) == _tree(_generate(second))
