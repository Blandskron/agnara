"""Every stated MCP SDK pin must be the one `agnara-mcp` declares.

#613 moved this pin from 2.1.1 to 2.2.0. The version was asserted in fourteen
tracked places and locating them took three passes: an audit truncated with
``head -20`` missed the runtime guard in ``tools/documentation_mcp/server.py``,
and the suite caught it instead.

A missed copy is not cosmetic. ``QUALITY_GATES.md`` quotes a ``uv pip install``
command a contributor is meant to run, so a stale version there sends them to a
different SDK than CI uses. The same mistake in the installed-artifact lane is
an unresolvable ``--no-index`` install, and in the documentation tool it is the
deliberately opaque ``stale_snapshot or size_limit`` refusal.

Only the ``mcp==<version>`` form asserts the current pin. Historical statements
are written differently on purpose -- ``REFERENCE_RESEARCH.md`` and ADR 0010 say
the pin *was* 2.1.1, and the recorded benchmark block says ``mcp 2.1.1`` -- so
the record of what used to be pinned keeps passing untouched.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

from tests.architecture.boundaries import WORKSPACE_ROOT, workspace_files

#: The package whose dependency table is the single authority for this pin.
AUTHORITY = Path("packages") / "agnara-mcp" / "pyproject.toml"

#: An assertion about the pin in force, as opposed to prose about an old one.
#: The lookbehind matters: \b also matches inside `agnara-mcp==1.0.3`,
#: which states a distribution version rather than this pin.
STATED_PIN = re.compile(r"(?<![\w-])mcp==(\d+\.\d+\.\d+)")

#: Derived from the authority on every run, so this module is never another copy.
DECLARED = re.compile(r"^mcp==(\d+\.\d+\.\d+)$")

SEARCHED_SUFFIXES = frozenset({".md", ".py", ".toml", ".txt", ".json", ".cfg", ".ini"})

#: Rendered from the sources above, so a mismatch here is a stale generator run,
#: which `scripts/render_agent_docs.py --check` already reports more precisely.
GENERATED = frozenset({"llms.txt", "llms-full.txt", "uv.lock"})


def declared_pin() -> str:
    document = tomllib.loads((WORKSPACE_ROOT / AUTHORITY).read_text(encoding="utf-8"))
    for dependency in document["project"]["dependencies"]:
        match = DECLARED.match(dependency)
        if match is not None:
            return match.group(1)
    raise AssertionError(f"{AUTHORITY.as_posix()} declares no exact mcp pin")


def searched_files() -> Iterator[Path]:
    """This checkout's own candidate files, never another worktree's.

    The first draft of this module walked the workspace itself and immediately
    read another agent's abandoned worktree, reporting eleven disagreements
    that were not in this tree at all -- the exact failure #611 fixed for the
    encoding scan. The shared walk in `boundaries` exists so that guard is
    written once.
    """
    for path in workspace_files(SEARCHED_SUFFIXES):
        if path.name not in GENERATED:
            yield path


def test_the_authority_declares_an_exact_pin() -> None:
    # A bounded or missing pin would make every check below vacuous.
    assert DECLARED.match(f"mcp=={declared_pin()}")


def test_every_stated_pin_matches_the_declaration() -> None:
    expected = declared_pin()
    disagreeing = []
    found = 0
    for path in searched_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for stated in STATED_PIN.findall(line):
                found += 1
                if stated != expected:
                    location = path.relative_to(WORKSPACE_ROOT).as_posix()
                    disagreeing.append(f"{location}:{number} states mcp=={stated}")

    # Locating the copies was the expensive part in #613, so name them.
    assert not disagreeing, (
        f"these files disagree with {AUTHORITY.as_posix()} (mcp=={expected}):\n"
        + "\n".join(disagreeing)
    )
    assert found > 1, "the search found no stated pin, so this guard proves nothing"
