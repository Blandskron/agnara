"""E0.9 ??? changelog and synchronized pre-one release invariants."""

from __future__ import annotations

import tomllib

from tests.architecture.boundaries import DISTRIBUTIONS, PACKAGES_DIR, WORKSPACE_ROOT


def _package_version(distribution: str) -> str:
    path = PACKAGES_DIR / distribution / "pyproject.toml"
    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    return project["version"]


def test_first_party_package_versions_are_synchronized() -> None:
    versions = {_package_version(distribution) for distribution in DISTRIBUTIONS}
    assert len(versions) == 1


def test_changelog_has_one_unreleased_section() -> None:
    changelog = (WORKSPACE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.count("## [Unreleased]") == 1


def test_changelog_uses_only_conventional_categories() -> None:
    changelog = (WORKSPACE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = {
        line.removeprefix("### ") for line in changelog.splitlines() if line.startswith("### ")
    }
    allowed = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
    assert headings <= allowed


def test_pull_request_template_requires_a_changelog_decision() -> None:
    template = (WORKSPACE_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    assert "## Changelog" in template
    assert "Added/updated an entry under `[Unreleased]`" in template
    assert "Not required; explanation provided below" in template
