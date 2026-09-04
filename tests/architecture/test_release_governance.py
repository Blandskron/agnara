"""E0.9 — changelog and synchronized pre-one release invariants."""

from __future__ import annotations

import re
import tomllib
from collections import Counter

from tests.architecture.boundaries import DISTRIBUTIONS, PACKAGES_DIR, WORKSPACE_ROOT

#: `([#96])` in an entry. The negative lookahead keeps the definition lines
#: themselves out of the "used" set.
REFERENCE = re.compile(r"\[(#\d+)\](?!:)")

#: `[#96]: https://github.com/Blandskron/agnara/issues/96` at the start of a line.
DEFINITION = re.compile(r"^\[(#\d+)\]:[ \t]*(\S+)$", re.MULTILINE)

ISSUE_URL = "https://github.com/Blandskron/agnara/issues/"


def _package_version(distribution: str) -> str:
    path = PACKAGES_DIR / distribution / "pyproject.toml"
    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    return project["version"]


def _changelog() -> str:
    return (WORKSPACE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_first_party_package_versions_are_synchronized() -> None:
    versions = {_package_version(distribution) for distribution in DISTRIBUTIONS}
    assert len(versions) == 1


def test_changelog_has_one_unreleased_section() -> None:
    changelog = (WORKSPACE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.count("## [Unreleased]") == 1


def test_changelog_has_no_unresolved_merge_markers() -> None:
    changelog = (WORKSPACE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    markers = ("<<<<<<<", "=======", ">>>>>>>")
    assert not any(marker in changelog for marker in markers)


def test_changelog_uses_only_conventional_categories() -> None:
    changelog = (WORKSPACE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = {
        line.removeprefix("### ") for line in changelog.splitlines() if line.startswith("### ")
    }
    allowed = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
    assert headings <= allowed


def test_every_changelog_reference_has_a_definition() -> None:
    changelog = _changelog()
    used = set(REFERENCE.findall(changelog))
    defined = {name for name, _ in DEFINITION.findall(changelog)}
    undefined = sorted(used - defined, key=lambda name: int(name[1:]))
    assert not undefined, f"changelog references render literally: {undefined}"


def test_no_changelog_definition_is_unreferenced() -> None:
    changelog = _changelog()
    used = set(REFERENCE.findall(changelog))
    defined = {name for name, _ in DEFINITION.findall(changelog)}
    orphans = sorted(defined - used, key=lambda name: int(name[1:]))
    assert not orphans, f"changelog defines links nothing uses: {orphans}"


def test_no_changelog_reference_is_defined_twice() -> None:
    counts = Counter(name for name, _ in DEFINITION.findall(_changelog()))
    duplicates = sorted(
        (name for name, count in counts.items() if count > 1), key=lambda name: int(name[1:])
    )
    assert not duplicates, f"changelog defines the same link twice: {duplicates}"


def test_every_changelog_definition_points_at_its_own_number() -> None:
    # A copy-pasted definition that keeps the previous number resolves to the
    # wrong Issue, which is worse than a link that visibly does not render.
    wrong = {
        name: url
        for name, url in DEFINITION.findall(_changelog())
        if url != f"{ISSUE_URL}{name[1:]}"
    }
    assert not wrong, f"changelog definitions do not match their number: {wrong}"


def test_the_unreleased_comparison_link_is_not_treated_as_an_issue_reference() -> None:
    # `[Unreleased]` is a compare link, not an Issue. If either pattern picked
    # it up, the orphan and number-matching rules would reject a correct file.
    assert "[Unreleased]: https://github.com/Blandskron/agnara/compare/" in _changelog()

    sample = "\n".join(
        [
            "## [Unreleased]",
            "- did a thing ([#42]).",
            "[Unreleased]: https://github.com/Blandskron/agnara/compare/main...develop",
            f"[#42]: {ISSUE_URL}42",
        ]
    )
    assert set(REFERENCE.findall(sample)) == {"#42"}
    assert [name for name, _ in DEFINITION.findall(sample)] == ["#42"]


def test_the_reference_link_rules_reject_each_defect() -> None:
    entry = "- did a thing ([#42])."
    definition = f"[#42]: {ISSUE_URL}42"

    missing = entry
    assert set(REFERENCE.findall(missing)) - {name for name, _ in DEFINITION.findall(missing)}

    orphan = definition
    assert {name for name, _ in DEFINITION.findall(orphan)} - set(REFERENCE.findall(orphan))

    duplicated = "\n".join([entry, definition, definition])
    assert Counter(name for name, _ in DEFINITION.findall(duplicated))["#42"] == 2

    mismatched = "\n".join([entry, f"[#42]: {ISSUE_URL}24"])
    assert [
        (name, url)
        for name, url in DEFINITION.findall(mismatched)
        if url != f"{ISSUE_URL}{name[1:]}"
    ]

    healthy = "\n".join([entry, definition])
    assert set(REFERENCE.findall(healthy)) == {name for name, _ in DEFINITION.findall(healthy)}


def test_pull_request_template_requires_a_changelog_decision() -> None:
    template = (WORKSPACE_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    assert "## Changelog" in template
    assert "Added/updated an entry under `[Unreleased]`" in template
    assert "Not required; explanation provided below" in template
