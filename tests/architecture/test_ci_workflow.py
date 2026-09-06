"""E0.8 — the CI workflow must run the documented quality gates.

``QUALITY_GATES.md`` names the commands that define "done". CI is the only
place those commands are proven, so a gate silently dropped from the
workflow would quietly lower the bar for every later change.

These are deliberately textual assertions: they need no YAML parser, and
they fail loudly if a gate is renamed or removed.
"""

from __future__ import annotations

import re

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT

WORKFLOW = WORKSPACE_ROOT / ".github" / "workflows" / "ci.yml"

#: The commands QUALITY_GATES.md lists as the required local checks.
REQUIRED_GATES = (
    "uv sync",
    "uv run ruff check",
    "uv run ruff format --check",
    "uv run ty check",
    "uv run pytest",
)

#: E0.8 asks for Linux, macOS and Windows where practical.
REQUIRED_PLATFORMS = ("ubuntu-latest", "macos-latest", "windows-latest")


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_ci_workflow_exists() -> None:
    assert WORKFLOW.is_file(), f"missing CI workflow at {WORKFLOW}"


@pytest.mark.parametrize("gate", REQUIRED_GATES)
def test_ci_runs_every_documented_quality_gate(gate: str, workflow_text: str) -> None:
    assert gate in workflow_text, (
        f"QUALITY_GATES.md requires {gate!r} but the CI workflow does not run it"
    )


@pytest.mark.parametrize("platform", REQUIRED_PLATFORMS)
def test_ci_covers_every_required_platform(platform: str, workflow_text: str) -> None:
    assert platform in workflow_text, f"E0.8 requires a {platform} lane"


def test_ci_verifies_the_python_314_baseline(workflow_text: str) -> None:
    """ADR 0001: CI must not silently pass on an older interpreter."""
    assert "uv python install 3.14" in workflow_text


def test_ci_enforces_the_lockfile(workflow_text: str) -> None:
    """An unlocked change would let CI and a developer resolve differently."""
    assert "uv lock --check" in workflow_text
    assert "uv sync --locked" in workflow_text


def test_ci_actions_are_pinned_to_exact_versions(workflow_text: str) -> None:
    """astral-sh/setup-uv stopped publishing floating major tags at v8.

    A floating tag would also silently change what runs in CI, so every
    action is pinned to an exact release.
    """
    used = [
        line.split("uses:", 1)[1].strip() for line in workflow_text.splitlines() if "uses:" in line
    ]
    assert used, "the workflow declares no actions"
    for action in used:
        _, _, version = action.partition("@")
        assert version.count(".") >= 2 or len(version) == 40, (
            f"{action} is not pinned to an exact release or commit SHA"
        )


def test_ci_grants_only_read_permissions_by_default(workflow_text: str) -> None:
    """SECURITY.md: the default posture is least privilege."""
    assert "permissions:\n  contents: read" in workflow_text


def test_ci_exposes_a_single_aggregate_status_check(workflow_text: str) -> None:
    """Branch protection needs one stable required check (E0B.4).

    Asserting the exact spelling of the `needs:` list only proved that nobody
    had edited that line. The invariant worth protecting is that the aggregate
    waits for *every* other job, so a job that runs but can never block a
    merge -- added without being made required -- fails here.
    """
    # Only the `jobs:` block: `on:` triggers sit at the same indentation.
    sections = re.split(r"^jobs:\s*$", workflow_text, maxsplit=1, flags=re.MULTILINE)
    assert len(sections) == 2, "the workflow declares no `jobs:` block"
    jobs_block = sections[1]
    jobs = re.findall(r"^  ([a-z][a-z0-9_-]*):$", jobs_block, re.MULTILINE)
    assert "ci" in jobs, f"no aggregate `ci` job among {jobs}"

    declared = re.search(r"^    needs: \[([^\]]*)\]$", jobs_block, re.MULTILINE)
    assert declared is not None, "the aggregate job declares no `needs:` list"
    required = {name.strip() for name in declared.group(1).split(",") if name.strip()}

    expected = set(jobs) - {"ci"}
    assert required == expected, (
        "the aggregate CI status must depend on every other job; "
        f"not required: {sorted(expected - required)}; "
        f"not a job: {sorted(required - expected)}"
    )


def test_documentation_browser_conformance_is_an_explicit_required_job(
    workflow_text: str,
) -> None:
    """E6.18 browser evidence must not disappear into ordinary skipped tests."""
    assert "browser:\n    name: Documentation browsers" in workflow_text
    assert "playwright install --with-deps chromium" in workflow_text
    assert 'AGNARA_RUN_BROWSER_TESTS: "1"' in workflow_text
    assert "pytest tests/http/test_documentation_browser.py -m browser" in workflow_text
    assert "pytest tests/http/test_explorer_browser.py -m browser" in workflow_text
