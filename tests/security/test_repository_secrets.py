"""A4-10: no real credential may live in the repository.

``scripts/check_distributions.py`` already scans what a wheel ships. It runs on
built artifacts, so it never sees the tests, fixtures, documentation and
workflow files that make up most of the repository -- and a credential
committed there is disclosed the moment the repository is cloned, whether or
not it was ever packaged.

The signatures are deliberately high-precision. A heuristic that flags every
string named ``password`` finds the vendored documentation bundles, which
contain OAuth *field* names rather than secrets, and a gate that has to be
argued with stops being read.
"""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]

#: Directories that hold no reviewed source: build output, virtual
#: environments, caches and local task artifacts.
SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        ".uv-cache",
        ".ruff_cache",
        ".pytest_cache",
        "__pycache__",
        "dist",
        "node_modules",
    }
)

#: Vendored documentation assets ship third-party example credential syntax and
#: carry their own hash and license gate, exactly as ``QUALITY_GATES.md`` and
#: the distribution checker record.
VENDORED = "/_vendor/"

#: File names that are a finding by their existence, whatever they contain.
FORBIDDEN_NAMES = frozenset({".env", ".pypirc", "id_rsa", "id_ed25519", ".netrc"})

CREDENTIALS = {
    # A PEM header alone is a fixture in this repository; a header followed by
    # encoded key material is a key.
    "private key": re.compile(
        rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----\s*\n[A-Za-z0-9+/=]{40}"
    ),
    "PyPI token": re.compile(rb"(?<![A-Za-z0-9_-])pypi-[A-Za-z0-9_-]{50,255}(?![A-Za-z0-9_-])"),
    "GitHub token": re.compile(rb"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{36,255}(?![A-Za-z0-9])"),
    "AWS access key": re.compile(rb"(?<![0-9A-Z])AKIA[0-9A-Z]{16}(?![0-9A-Z])"),
    "Slack token": re.compile(rb"xox[abprs]-[A-Za-z0-9]{10,}-[A-Za-z0-9-]{10,}"),
    "Google API key": re.compile(rb"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{35}(?![A-Za-z0-9_-])"),
    "signed token": re.compile(
        rb"eyJ[A-Za-z0-9_-]{16,}\.eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"
    ),
}


def reviewed_files() -> list[Path]:
    """Every file a clone of this repository would carry."""
    found: list[Path] = []
    for path in REPOSITORY.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(REPOSITORY).as_posix()
        if any(part in SKIPPED_DIRECTORIES for part in path.parts):
            continue
        if relative.startswith(".artifacts") or relative.startswith(".release-validation"):
            continue
        found.append(path)
    return found


def test_the_repository_carries_no_credential() -> None:
    """No reviewed file matches a recognized credential format."""
    findings: list[str] = []
    for path in reviewed_files():
        relative = path.relative_to(REPOSITORY).as_posix()
        if VENDORED in f"/{relative}":
            continue
        try:
            payload = path.read_bytes()
        except OSError:  # pragma: no cover - unreadable file is not a secret
            continue
        for kind, pattern in CREDENTIALS.items():
            match = pattern.search(payload)
            if match is not None:
                line = payload[: match.start()].count(b"\n") + 1
                findings.append(f"{relative}:{line} looks like a {kind}")

    assert findings == []


def test_no_credential_bearing_file_is_committed() -> None:
    """A credential file is a finding by name, before anyone reads it."""
    named = [
        path.relative_to(REPOSITORY).as_posix()
        for path in reviewed_files()
        if path.name in FORBIDDEN_NAMES
    ]

    assert named == []


def test_the_scan_actually_reaches_the_repository() -> None:
    """A gate that silently scans nothing is worse than no gate.

    ``reviewed_files`` walks a computed root and skips several trees, so it is
    checked against files that must always be there.
    """
    found = {path.relative_to(REPOSITORY).as_posix() for path in reviewed_files()}

    assert "SECURITY.md" in found
    assert "docs/THREAT_MODEL.md" in found
    assert "packages/agnara-http/src/agnara_http/composition.py" in found
    assert len(found) > 200


def test_a_planted_credential_would_be_caught(tmp_path: Path) -> None:
    """The signatures match a real credential shape, not only their own names."""
    planted = tmp_path / "leak.txt"
    planted.write_bytes(b"AKIA" + b"ABCDEFGHIJKLMNOP")

    assert CREDENTIALS["AWS access key"].search(planted.read_bytes()) is not None
    assert CREDENTIALS["AWS access key"].search(b"NOTAKIAABCDEFGHIJKLMNOP") is None
