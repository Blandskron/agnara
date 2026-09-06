"""The planning documents still describe this repository.

`docs/MATURITY.md` claims what exists. A claim about a repository can outlive
the code that made it true, and the whole reason that file is authoritative is
that a reader should not have to check. So the parts a machine can check are
checked here.

This is deliberately narrow. It verifies that the documents refer to things
that exist and that their vocabulary is internally consistent -- it cannot
verify that `IMPLEMENTED` is honest, which stays a human judgement recorded in
review. Testing the checkable part is what keeps the unverifiable part
credible.
"""

from __future__ import annotations

import importlib
import re

import pytest

from tests.architecture.boundaries import DISTRIBUTIONS, WORKSPACE_ROOT

MATURITY = WORKSPACE_ROOT / "docs" / "MATURITY.md"
INITIATIVES = WORKSPACE_ROOT / "docs" / "INITIATIVES.md"
TARGET = WORKSPACE_ROOT / "docs" / "TARGET_ARCHITECTURE.md"
MAP = WORKSPACE_ROOT / "docs" / "DOCUMENTATION_MAP.md"
ROADMAP = WORKSPACE_ROOT / "ROADMAP.md"

PLANNING_DOCUMENTS = (MATURITY, INITIATIVES, TARGET, MAP, ROADMAP)

#: The vocabulary `docs/MATURITY.md` declares. A status outside this set means
#: either the table or the vocabulary drifted, and either way a reader now has
#: to guess -- which is the thing the vocabulary exists to prevent.
STATUSES = frozenset(
    {
        "IMPLEMENTED",
        "EXPERIMENTAL",
        "DESIGNED",
        "PLANNED",
        "RESEARCH",
        "DEFERRED",
        "DEPRECATED",
        "REMOVED",
    }
)

#: Matches a distribution row of the table in `docs/MATURITY.md`:
#: | `name` | `STATUS` | published | public names | notes |
_DISTRIBUTION_ROW = re.compile(
    r"^\| `(agnara[a-z0-9-]*)` \| `([A-Z]+)` \| (\w+) \| (\d+) \|", re.MULTILINE
)


def declared_public_names() -> dict[str, int]:
    """Public-name counts read *from* the table, not transcribed beside it.

    Parsing the document is what makes the table itself the thing under test.
    A copy kept in this file would let the two drift while every test passed,
    which is the failure mode the table exists to prevent.
    """
    rows = {
        match.group(1): int(match.group(4)) for match in _DISTRIBUTION_ROW.finditer(read(MATURITY))
    }
    assert rows, "no distribution rows were parsed from docs/MATURITY.md"
    return rows


def read(path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def maturity() -> str:
    return read(MATURITY)


# ---------------------------------------------------------------------------
# The documents exist and reference things that exist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("document", PLANNING_DOCUMENTS, ids=lambda path: path.name)
def test_the_canonical_planning_documents_exist(document) -> None:
    assert document.is_file(), document


@pytest.mark.parametrize("document", PLANNING_DOCUMENTS, ids=lambda path: path.name)
def test_no_planning_document_references_a_missing_repository_file(document) -> None:
    """A pointer to a deleted document is worse than no pointer at all."""
    referenced = set(
        re.findall(r"`((?:docs/|tests/|packages/)[A-Za-z0-9_./-]+\.[a-z]+)`", read(document))
    )
    assert referenced, f"{document.name} cites no repository path; the check would be vacuous"

    missing = sorted(path for path in referenced if not (WORKSPACE_ROOT / path).exists())
    assert not missing, f"{document.name} references files that do not exist: {missing}"


@pytest.mark.parametrize("document", PLANNING_DOCUMENTS, ids=lambda path: path.name)
def test_every_referenced_decision_record_exists(document) -> None:
    """`ADR 0065` and `RFC 0002` are citations; a dangling one misleads.

    Only zero-padded numbers are Agnara records. `RFC 9457` is the IETF
    problem-details document, and the repository cites both kinds with the
    same word -- so the leading zero is what distinguishes them.
    """
    text = read(document)
    for kind, folder in (("ADR", "adr"), ("RFC", "rfc")):
        numbers = set(re.findall(rf"\b{kind} (0\d{{3}})\b", text))
        for number in sorted(numbers):
            matches = list((WORKSPACE_ROOT / "docs" / folder).glob(f"{number}-*.md"))
            assert matches, f"{document.name} cites {kind} {number}, which does not exist"


# ---------------------------------------------------------------------------
# The maturity table matches the repository
# ---------------------------------------------------------------------------


def test_every_status_token_is_in_the_declared_vocabulary(maturity: str) -> None:
    """A status is read from the Status column, not from anywhere shouty.

    The table also names things like `SINGLETON` and `INVOCATION`, which are
    dependency scopes rather than statuses. Reading only the column that means
    "status" is what makes a typo detectable without flagging vocabulary that
    belongs to another subsystem.
    """
    used = {
        match.group(1)
        for match in re.finditer(r"^\|[^|]+\| `([A-Z][A-Z0-9-]+)`", maturity, re.MULTILINE)
    }
    assert used, "no status column was found in docs/MATURITY.md"

    unknown = sorted(used - STATUSES)
    assert not unknown, f"statuses outside the declared vocabulary: {unknown}"


def test_the_table_lists_every_distribution(maturity: str) -> None:
    missing = sorted(name for name in DISTRIBUTIONS if f"`{name}`" not in maturity)
    assert not missing, f"distributions absent from docs/MATURITY.md: {missing}"


def test_the_table_invents_no_distribution() -> None:
    assert set(declared_public_names()) == set(DISTRIBUTIONS), (
        "docs/MATURITY.md names distributions the workspace does not have, or omits some"
    )


@pytest.mark.parametrize("distribution", sorted(DISTRIBUTIONS))
def test_the_declared_public_surface_matches_the_package(distribution: str) -> None:
    """A package cannot gain or lose a public surface without saying so.

    This is the one number in the table a machine can hold to account, and it
    is the number that matters most: it is what distinguishes an implemented
    adapter from a reserved namespace.
    """
    declared = declared_public_names()[distribution]
    module = importlib.import_module(distribution.replace("-", "_"))
    exported = getattr(module, "__all__", None)
    assert exported is not None, f"{distribution} declares no __all__"
    assert len(exported) == declared, (
        f"{distribution} exports {len(exported)} names; docs/MATURITY.md says {declared}"
    )


def test_the_reserved_namespaces_are_still_reserved(maturity: str) -> None:
    """`agnara-a2a` and `agnara-events` are documented as having no runtime.

    If either grows an implementation, its row stops being true, and this is
    the cheapest place to notice.
    """
    for distribution in ("agnara-a2a", "agnara-events"):
        module = importlib.import_module(distribution.replace("-", "_"))
        assert getattr(module, "__all__", None) == [], (
            f"{distribution} now exports something; update docs/MATURITY.md"
        )


# ---------------------------------------------------------------------------
# The planning documents agree with each other
# ---------------------------------------------------------------------------


def test_every_initiative_the_roadmap_cites_is_defined() -> None:
    """The roadmap points at initiatives; a dangling id sends a reader nowhere."""
    defined = set(re.findall(r"^### (I\d+) ", read(INITIATIVES), re.MULTILINE))
    assert defined, "docs/INITIATIVES.md defines no initiatives"

    cited = set(re.findall(r"\b(I\d+)\b", read(ROADMAP)))
    dangling = sorted(cited - defined)
    assert not dangling, f"ROADMAP.md cites undefined initiatives: {dangling}"


def test_every_initiative_declares_a_horizon_and_a_status() -> None:
    text = read(INITIATIVES)
    sections = re.split(r"^### (I\d+) ", text, flags=re.MULTILINE)[1:]
    pairs = list(zip(sections[::2], sections[1::2], strict=True))
    assert pairs, "docs/INITIATIVES.md defines no initiatives"

    incomplete = [
        identifier
        for identifier, body in pairs
        if "**Horizon:**" not in body or "**Status:**" not in body
    ]
    assert not incomplete, f"initiatives missing a horizon or status: {incomplete}"


def test_the_documentation_map_names_documents_that_exist() -> None:
    """The map is only useful while every owner it names is real."""
    owners = set(re.findall(r"`([A-Za-z0-9_./-]+\.md)`", read(MAP)))
    assert owners, "docs/DOCUMENTATION_MAP.md names no owning documents"

    missing = sorted(
        name
        for name in owners
        if not (WORKSPACE_ROOT / name).exists() and not (WORKSPACE_ROOT / "docs" / name).exists()
    )
    assert not missing, f"the documentation map names missing documents: {missing}"
