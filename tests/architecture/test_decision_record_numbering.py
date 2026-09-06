"""A decision record's number must identify exactly one document.

ADRs and RFCs are cited by number across the documentation ("RFC 0004",
"ADR 0021"). Two files sharing a number make every such citation ambiguous,
and the ambiguity is invisible until a reader follows one. RFC 0004 was
duplicated between the dependency-injection RFC (#45) and the
protocol-neutral delegation RFC (#102) until the latter became RFC 0005.
"""

import re
from collections import defaultdict

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT

#: Files are named `NNNN-slug.md`; the number is the citable identifier.
_NUMBERED = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")

RECORD_DIRECTORIES = ("docs/adr", "docs/rfc")


def records(directory: str) -> list[tuple[str, str]]:
    """(number, filename) for every numbered record in `directory`."""
    root = WORKSPACE_ROOT / directory
    found = []
    for path in sorted(root.iterdir()):
        if path.name.lower() == "readme.md" or not path.is_file():
            continue
        match = _NUMBERED.match(path.name)
        assert match is not None, f"{directory}/{path.name} is not named NNNN-slug.md"
        found.append((match.group(1), path.name))
    return found


@pytest.mark.parametrize("directory", RECORD_DIRECTORIES)
def test_a_number_identifies_one_record(directory: str) -> None:
    by_number: dict[str, list[str]] = defaultdict(list)
    for number, name in records(directory):
        by_number[number].append(name)
    collisions = {number: names for number, names in by_number.items() if len(names) > 1}
    assert not collisions, f"duplicate {directory} numbers: {collisions}"


@pytest.mark.parametrize("directory", RECORD_DIRECTORIES)
def test_a_record_titles_itself_with_its_own_number(directory: str) -> None:
    """A renamed file whose heading still claims the old number is worse than
    the collision it was renamed to fix: the citation and the title disagree.
    """
    mismatched = []
    for number, name in records(directory):
        heading = (WORKSPACE_ROOT / directory / name).read_text(encoding="utf-8").split("\n", 1)[0]
        if number not in heading:
            mismatched.append(f"{name} -> {heading!r}")
    assert not mismatched, f"{directory} records whose heading omits their number: {mismatched}"
