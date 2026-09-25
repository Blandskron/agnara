"""Current documentation must resolve locally and avoid superseded release prose."""

from __future__ import annotations

import re
from urllib.parse import unquote

from tests.architecture.boundaries import WORKSPACE_ROOT

ROOT_DOCS = [
    WORKSPACE_ROOT / name
    for name in (
        "README.md",
        "ROADMAP.md",
        "BACKLOG.md",
        "CHANGELOG.md",
        "SECURITY.md",
        "QUALITY_GATES.md",
        "AGENTS.md",
        "AGENT_OPERATING_MODEL.md",
        "MULTI_AGENT_PROTOCOL.md",
        "GIT_WORKFLOW.md",
    )
]
DOCS = (
    ROOT_DOCS
    + sorted((WORKSPACE_ROOT / "docs").rglob("*.md"))
    + sorted((WORKSPACE_ROOT / "packages").glob("*/README.md"))
)
RELEASE_TOOLING = [
    WORKSPACE_ROOT / name
    for name in (
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        "scripts/check_public_imports.py",
        "scripts/check_publication_readiness.py",
        "scripts/check_release_preconditions.py",
        "scripts/check_release_readiness.py",
        "scripts/distributions.py",
        "scripts/set_workspace_version.py",
    )
]
SUPERSEDED = re.compile(
    r"\b0\.1\.0a[2-9]\b|\bA[2-9]\b|\b1\.0\.[012]\b|\bV1-\d+\b|"
    r"RELEASE_PLAN\.md|MIGRATION_A8_TO_1_0\.md|"
    r"publication recovery|retained baseline|working toward (?:its )?first stable",
    re.IGNORECASE,
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def test_live_documentation_has_no_superseded_release_claims() -> None:
    stale: list[str] = []
    for document in [*DOCS, *RELEASE_TOOLING]:
        if document.name == "CHANGELOG.md":
            continue  # The compare URL legitimately starts at the last published tag.
        for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
            if SUPERSEDED.search(line):
                stale.append(f"{document.relative_to(WORKSPACE_ROOT)}:{number}: {line.strip()}")
    assert not stale, "Superseded release documentation:\n" + "\n".join(stale)


def test_local_markdown_links_resolve() -> None:
    broken: list[str] = []
    for document in DOCS:
        for raw in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            target = raw.split()[0].strip("<>")
            if target.startswith(("http:", "https:", "mailto:", "#", "codex:")):
                continue
            path = unquote(target.split("#", 1)[0])
            if not path:
                continue
            destination = (document.parent / path).resolve()
            if not destination.is_file():
                broken.append(f"{document.relative_to(WORKSPACE_ROOT)} -> {target}")
    assert not broken, "Broken local Markdown links:\n" + "\n".join(broken)


def test_only_current_release_document_set_remains() -> None:
    actual = {path.name for path in (WORKSPACE_ROOT / "docs" / "releases").iterdir()}
    expected = {
        "README.md",
        "RELEASE_CHECKLIST.md",
        "v1.0.3.md",
        "release-status.json",
        "publication.json",
    }
    assert actual == expected
