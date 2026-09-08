"""Exercise publication ancestry against real isolated Git histories."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[2] / "scripts" / "check_release_tag.py"


@pytest.mark.parametrize("case", ["accepted", "wrong-branch", "lightweight", "wrong-checkout"])
def test_release_tag_boundary(tmp_path: Path, case: str) -> None:
    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments], cwd=tmp_path, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init")
    git("config", "user.name", "Release test")
    git("config", "user.email", "release-test@example.invalid")
    git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "accepted main")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    if case == "wrong-branch":
        git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "unmerged work")
    if case == "lightweight":
        git("-c", "tag.gpgsign=false", "tag", "v0.1.0a4")
    else:
        git("-c", "tag.gpgsign=false", "tag", "-a", "v0.1.0a4", "-m", "A4")
    if case == "wrong-checkout":
        git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "later main")
        git("update-ref", "refs/remotes/origin/main", "HEAD")
    result = subprocess.run(
        [sys.executable, str(CHECKER), "v0.1.0a4"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == (0 if case == "accepted" else 1), result.stdout + result.stderr
