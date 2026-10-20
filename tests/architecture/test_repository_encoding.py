"""Repository-integrity guard against lossy text encoding.

Twice in this repository's history a tool wrote UTF-8 documentation through a
cp1252 encoder with ``errors="replace"`` and committed the result, destroying
every em-dash, arrow and box-drawing character it touched. ``README.md`` lost
all of its diagrams that way. See GitHub Issue #123.

Five signatures are checked, because they are what the known failure modes
leave behind:

- a run of consecutive literal question marks, from ``errors="replace"`` while
  encoding to a codec that cannot represent the character;
- U+00E2 followed by U+20AC, and its doubly-applied form U+00C3 U+00A2, from
  UTF-8 bytes decoded as cp1252 and re-encoded;
- U+FFFD, from ``errors="replace"`` while decoding;
- a UTF-8 byte-order mark, which a Windows PowerShell ``Out-File`` writes
  by default and which ``.gitattributes`` normalization does not strip;
- a NUL or other C0 control byte, which is what a mangled multi-byte
  character can decay into and which makes Git treat the file as binary.

The last two were added after ``ROADMAP.md`` was rewritten through a lossy
Windows pipeline during the pre-``0.1.0a4`` cleanup. That damage replaced
each em-dash with a single ``?`` plus a quote and each following ``0`` with
a NUL, so the consecutive-question-mark pattern did not match -- and a NUL
is valid UTF-8, so the file passed every check here while rendering as
mojibake and diffing as binary.

Every pattern here is built from escapes so that this module does not match
itself and is therefore exempt from its own rule. Do not inline the damaged
characters in this file.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT

#: Two or more consecutive question marks. Verified to have no legitimate
#: occurrence in this repository. A genuine one would need an explicit
#: exclusion with a stated reason, not a weaker pattern.
REPLACED_RUN = re.compile(r"\?{2,}")

#: UTF-8 read as cp1252. U+00E2 U+20AC is the mojibake prefix shared by the
#: en-dash, em-dash and curly quotes; U+00C3 U+00A2 is the same damage applied
#: a second time.
CP1252_MISREAD = re.compile("\u00e2\u20ac|\u00c3\u00a2")

#: The Unicode replacement character, left behind by a lossy decode.
REPLACEMENT_CHARACTER = "\ufffd"

#: A UTF-8 byte-order mark. This repository stores UTF-8 without one.
BYTE_ORDER_MARK = b"\xef\xbb\xbf"

#: The only C0 controls that legitimately appear in text. Any other
#: control character in a text file is damage.
ALLOWED_CONTROL_CHARACTERS = frozenset({"\t", "\n", "\r"})

TEXT_SUFFIXES = frozenset({".md", ".py", ".toml", ".json", ".yml", ".yaml", ".txt", ".cfg", ".ini"})

SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".uv-cache",
        ".venv",
        "__pycache__",
        "dist",
        "node_modules",
    }
)


def _is_nested_working_tree(directory: Path) -> bool:
    """Report whether ``directory`` is the root of another Git working tree.

    ``MULTI_AGENT_PROTOCOL.md`` has concurrent agents isolate their work with
    ``git worktree``. A worktree created inside this checkout holds another
    agent's files, often half-written, and scanning them reports damage that
    does not exist in the tree under review. A linked worktree and a submodule
    mark their root with a ``.git`` *file* naming the real repository; a nested
    clone marks it with a ``.git`` directory. Detecting that marker rather than
    a directory name keeps the guard working whatever the worktree is called.
    """
    return (directory / ".git").exists()


def _own_text_files(directory: Path) -> Iterator[Path]:
    """Yield text files under ``directory``, pruning trees this one does not own."""
    for entry in sorted(directory.iterdir()):
        if entry.name in SKIPPED_DIRECTORIES:
            continue
        if entry.is_dir():
            # ``rglob`` does not descend into symlinked directories either:
            # following one risks a cycle and files owned somewhere else.
            if entry.is_symlink() or _is_nested_working_tree(entry):
                continue
            yield from _own_text_files(entry)
        elif entry.is_file() and entry.suffix.lower() in TEXT_SUFFIXES:
            yield entry


def text_files() -> Iterator[Path]:
    """Yield the workspace's own text files in a deterministic order."""
    yield from _own_text_files(WORKSPACE_ROOT)


def _location(path: Path) -> str:
    return path.relative_to(WORKSPACE_ROOT).as_posix()


def test_the_workspace_has_text_files_to_check() -> None:
    # A silently empty walk would make every check below vacuous.
    names = {path.name for path in text_files()}
    assert {"README.md", "BACKLOG.md", "pyproject.toml"} <= names


def test_the_walk_stops_at_another_working_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worktree, submodule or clone nested in the checkout is not ours to judge.

    Agents working in parallel put a linked worktree inside the checkout, and
    before this guard existed its files entered the scan: one run pulled 611
    files belonging to another agent's half-finished task into these checks.
    The damage they would report is not damage in the tree under review.
    """
    (tmp_path / "own.md").write_text("# Ours\n", encoding="utf-8")

    linked = tmp_path / ".worktrees" / "issue-610"
    linked.mkdir(parents=True)
    # What `git worktree add` writes: a file, not a directory.
    (linked / ".git").write_text("gitdir: ../../.git/worktrees/issue-610\n", encoding="utf-8")
    (linked / "theirs.md").write_text("# Theirs\n", encoding="utf-8")

    clone = tmp_path / "vendored"
    (clone / ".git").mkdir(parents=True)
    (clone / "theirs.md").write_text("# Theirs\n", encoding="utf-8")

    monkeypatch.setattr("tests.architecture.test_repository_encoding.WORKSPACE_ROOT", tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in text_files()] == ["own.md"]


def test_every_text_file_is_valid_utf8() -> None:
    undecodable = []
    for path in text_files():
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            undecodable.append(_location(path))
    assert not undecodable, f"not valid UTF-8: {undecodable}"


def test_no_text_file_contains_replaced_characters() -> None:
    damaged = []
    for path in text_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if REPLACED_RUN.search(line):
                damaged.append(f"{_location(path)}:{number}: {line.strip()[:80]}")
    assert not damaged, "characters replaced by a lossy encoder:\n" + "\n".join(damaged)


def test_no_text_file_contains_cp1252_misread_sequences() -> None:
    damaged = []
    for path in text_files():
        text = path.read_text(encoding="utf-8")
        if CP1252_MISREAD.search(text) or REPLACEMENT_CHARACTER in text:
            damaged.append(_location(path))
    assert not damaged, f"UTF-8 decoded as cp1252, or a lossy decode: {damaged}"


def test_no_text_file_starts_with_a_byte_order_mark() -> None:
    """A BOM is how a Windows-default text write announces itself.

    It also breaks a tool that expects a bare ``#`` or ``---`` as the first
    byte, and it is invisible in every editor that would otherwise show it.
    """
    marked = [
        _location(path) for path in text_files() if path.read_bytes().startswith(BYTE_ORDER_MARK)
    ]
    assert not marked, f"UTF-8 byte-order mark present: {marked}"


def _control_characters(line: str) -> list[str]:
    """The damaging control characters in `line`, in codepoint order."""
    return sorted(
        {
            character
            for character in line
            if character < " " and character not in ALLOWED_CONTROL_CHARACTERS
        }
    )


def test_no_text_file_contains_a_control_character() -> None:
    """A NUL in Markdown is a mangled character, and Git then calls it
    binary.

    This is the signature the consecutive-question-mark pattern misses: a
    lossy single-character substitution leaves one ``?`` behind, not a run.
    """
    damaged = []
    for path in text_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = _control_characters(line)
            if found:
                codepoints = ", ".join(f"U+{ord(character):04X}" for character in found)
                damaged.append(f"{_location(path)}:{number}: {codepoints}")
    assert not damaged, "control characters in text files:\n" + "\n".join(damaged)


def test_the_guard_recognizes_each_known_failure_mode() -> None:
    # Rebuild the damage from escapes rather than trusting that the patterns
    # are ever exercised by a real regression.
    once_replaced = "EPIC 0 " + "?" * 8 + " Repository foundation"
    once_misread = "Agnara \u00e2\u20ac\u201d a capability-first kernel"
    twice_misread = "Agnara \u00c3\u00a2\u00e2\u201a¬ a kernel"
    lossy_decode = f"Agnara {REPLACEMENT_CHARACTER} a capability-first kernel"

    assert REPLACED_RUN.search(once_replaced)
    assert CP1252_MISREAD.search(once_misread)
    assert CP1252_MISREAD.search(twice_misread)
    assert REPLACEMENT_CHARACTER in lossy_decode

    # The ROADMAP.md mode: one substituted character rather than a run.
    single = '### NOW ?" \x00.1.0a4, Application'
    assert not REPLACED_RUN.search(single), "a single substitution is why the control check exists"
    assert _control_characters(single)
    assert ("\ufeff# Roadmap").encode("utf-8").startswith(BYTE_ORDER_MARK)


def test_the_guard_does_not_fire_on_legitimate_text() -> None:
    assert not REPLACED_RUN.search("EPIC 0 — Repository foundation")
    assert not REPLACED_RUN.search("Is this the right boundary? Probably.")
    assert not CP1252_MISREAD.search("MCP ───► Capability ◄─── A2A")
    assert not CP1252_MISREAD.search("├── packages/")
    assert not _control_characters("tabs\tand newlines are ordinary")
    assert not (b"# Roadmap").startswith(BYTE_ORDER_MARK)
