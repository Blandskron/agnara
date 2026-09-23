"""E0.8 — the CI workflow must run the documented quality gates.

``QUALITY_GATES.md`` names the commands that define "done". CI is the only
place those commands are proven, so a gate silently dropped from the
workflow would quietly lower the bar for every later change.

These are deliberately textual assertions: they need no YAML parser, and
they fail loudly if a gate is renamed or removed.
"""

from __future__ import annotations

import re
from pathlib import Path

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
    assert "pytest tests/http/test_documentation_browser.py" in workflow_text
    assert "tests/http/test_public_documentation_browser.py -m browser" in workflow_text
    assert "pytest tests/http/test_explorer_browser.py -m browser" in workflow_text


def test_security_analysis_is_bounded_and_cannot_skip_the_required_gate(workflow_text: str) -> None:
    """A4-R3: scanning runs without application execution or broad write access."""
    security = workflow_text.split("  security:\n", 1)[1].split("  lint:\n", 1)[0]
    assert "language: [python, actions]" in security
    assert "build-mode: none" in security
    assert "persist-credentials: false" in security
    assert "      contents: read\n      security-events: write" in security
    assert "id-token:" not in security
    assert "secrets:" not in security
    assert "continue-on-error" not in security
    assert "pull_request_target" not in workflow_text
    assert "contains(needs.*.result, 'skipped')" in workflow_text
    for action in ("init", "analyze"):
        assert re.search(rf"github/codeql-action/{action}@[0-9a-f]{{40}}", security)


# ---------------------------------------------------------------------------
# Every workflow, not just this one
# ---------------------------------------------------------------------------

WORKFLOW_DIRECTORY = WORKSPACE_ROOT / ".github" / "workflows"

#: A third-party action reference: `owner/repo[/path]@ref`. A local reusable
#: workflow (`./.github/workflows/ci.yml`) has no `@` and is this repository's
#: own reviewed content, so it is not a supply-chain reference.
_USES = re.compile(r"^\s*-?\s*uses:\s*(?P<action>[^\s#]+)", re.MULTILINE)


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOW_DIRECTORY.glob("*.yml")) + sorted(WORKFLOW_DIRECTORY.glob("*.yaml"))


def test_there_is_a_workflow_to_check() -> None:
    """A silently empty glob would make the rule below vacuous."""
    assert _workflow_files()


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda path: path.name)
def test_every_workflow_pins_third_party_actions_to_a_commit_sha(workflow: Path) -> None:
    """A version tag is mutable, and this rule was only enforced on two files.

    `test_ci_actions_are_pinned_to_exact_versions` reads `ci.yml`, and the
    release suite reads `release.yml`. `agent-coordination.yml` was covered by
    neither and used `actions/checkout@v7` and `actions/setup-python@v7`: two
    floating major tags, re-pointable by whoever controls those repositories,
    executing on every push to `develop` and `main` and on every pull request.

    The older rule also accepted any reference with two dots, so `@v7.0.1`
    would have satisfied it. A tag can be moved whatever it is called, so this
    requires the 40-character commit SHA the rest of the repository already
    uses.
    """
    text = workflow.read_text(encoding="utf-8")
    offenders = []
    for match in _USES.finditer(text):
        action = match.group("action")
        if action.startswith("./"):
            continue
        _, separator, reference = action.partition("@")
        if not separator or not re.fullmatch(r"[0-9a-f]{40}", reference):
            offenders.append(action)

    assert not offenders, (
        f"{workflow.name} references actions that are not pinned to a commit SHA: {offenders}"
    )


@pytest.mark.parametrize("workflow", _workflow_files(), ids=lambda path: path.name)
def test_every_workflow_names_the_version_behind_each_pin(workflow: Path) -> None:
    """A bare SHA is unreviewable; the trailing comment is what makes it legible."""
    text = workflow.read_text(encoding="utf-8")
    unlabelled = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"uses:\s*[^\s#]+@[0-9a-f]{40}\s*$", line)
    ]

    assert not unlabelled, f"{workflow.name} pins without naming the version: {unlabelled}"
