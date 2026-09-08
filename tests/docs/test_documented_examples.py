"""A4-12: documentation that shows a complete program must run.

Prose goes stale quietly. Code does not, once something executes it. These
tests take the fenced blocks that documentation presents as complete programs,
run them exactly as written, and fail when the documented spelling stops
working.

Only blocks a reader could paste and run are listed. An excerpt that continues
an earlier example is not one of those, and pretending otherwise would force
documentation into a shape that reads worse. `EXECUTABLE` is therefore an
explicit allowlist keyed by the heading each block sits under, so adding a
runnable example to a page is a deliberate act rather than an accident of
formatting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]

#: (document, heading) pairs whose Python block must run unchanged.
EXECUTABLE: tuple[tuple[str, str], ...] = (
    ("packages/agnara/README.md", "Quick start"),
    ("packages/agnara-mcp/README.md", "Execution plans"),
    ("docs/releases/v0.1.0a4.md", "4. Apps and bounded contexts"),
    ("docs/releases/v0.1.0a4.md", "6. Serving over HTTP"),
)


def blocks_by_heading(path: Path, language: str = "python") -> dict[str, str]:
    """Map each heading to the last fenced block of `language` beneath it."""
    found: dict[str, str] = {}
    heading = "(no heading)"
    current: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if current is None:
            if stripped.startswith("#"):
                heading = stripped.lstrip("# ").strip()
            elif stripped == f"```{language}":
                current = []
            continue
        if stripped == "```":
            found[heading] = "\n".join(current) + "\n"
            current = None
            continue
        current.append(line)
    return found


@pytest.mark.parametrize(("document", "heading"), EXECUTABLE)
def test_a_documented_program_runs_as_written(document: str, heading: str) -> None:
    """Execute the block verbatim; any exception is documentation drift."""
    path = REPOSITORY / document
    assert path.is_file(), f"{document} does not exist"

    found = blocks_by_heading(path)
    assert heading in found, f"{document} has no Python block under {heading!r}"

    namespace: dict[str, object] = {"__name__": "__agnara_documented_example__"}
    compiled = compile(found[heading], f"{document}#{heading}", "exec")
    # Running the documentation is the test: the block is repository-owned
    # Markdown, read from disk, never caller input.
    exec(compiled, namespace)


def test_every_listed_document_exists_and_is_reachable() -> None:
    """A renamed document must fail here rather than silently stop being checked."""
    for document, _ in EXECUTABLE:
        assert (REPOSITORY / document).is_file(), document
