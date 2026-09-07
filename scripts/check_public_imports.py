"""Audit source files for imports that leave Agnara's governed public API.

This is the mechanical answer to the `0.1.0a4` question "can Agnara be consumed
as a framework from outside this repository?". An application that has to reach
into `agnara_http._dispatch` is not consuming a framework; it is patching one.
Rather than trusting a reviewer to notice, this script decides it from
`docs/public-api.json`: an import is supported when the module it names is
classified and the name it pulls out of that module is classified too.

It is deliberately usable on trees outside this workspace::

    python scripts/check_public_imports.py path/to/an/application

so the reference applications built for `0.1.0a4` can be audited with the same
rule the repository holds its own examples to, and a finding is a framework
defect to fix rather than an application detail to hide.

Markdown is audited as well as Python, because a guide that teaches a private
import is worse than code that performs one: the code breaks once, the guide
keeps producing broken code.

Uses the standard library only, like the rest of the repository's own tooling.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "public-api.json"

#: A fenced Markdown block, with the language tag it declares.
FENCE = re.compile(r"^```([A-Za-z0-9_+-]*)\s*$")

#: Languages whose fenced blocks are read as Python.
PYTHON_FENCES = frozenset({"python", "py", "python3"})

#: An import line recovered from a Markdown block that does not parse whole.
#: Guides routinely show fragments, and a fragment still teaches an import.
IMPORT_LINE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\s+(.+)|import\s+([\w.]+))")


@dataclass(frozen=True, slots=True)
class Finding:
    """One import that the public API manifest does not support."""

    path: Path
    lineno: int
    statement: str
    reason: str

    def render(self, relative_to: Path) -> str:
        try:
            where = self.path.relative_to(relative_to).as_posix()
        except ValueError:  # pragma: no cover - a path outside the anchor
            where = self.path.as_posix()
        return f"{where}:{self.lineno}: {self.statement} -- {self.reason}"

    def as_dict(self, relative_to: Path) -> dict[str, object]:
        try:
            where = self.path.relative_to(relative_to).as_posix()
        except ValueError:  # pragma: no cover - a path outside the anchor
            where = self.path.as_posix()
        return {
            "path": where,
            "line": self.lineno,
            "statement": self.statement,
            "reason": self.reason,
        }


class Surface:
    """The governed public API, as the manifest declares it."""

    def __init__(self, exports: dict[str, frozenset[str]], roots: frozenset[str]) -> None:
        self._exports = exports
        self._roots = roots

    @classmethod
    def from_manifest(cls, path: Path) -> Surface:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 3:
            raise ValueError(f"{path}: public API manifest must use schema_version 3")
        exports: dict[str, frozenset[str]] = {}
        roots: set[str] = set()
        for entry in document["distributions"]:
            roots.add(entry["import_name"])
            for module in entry["modules"]:
                exports[module["module"]] = frozenset(item["name"] for item in module["exports"])
        return cls(exports, frozenset(roots))

    def owns(self, module: str) -> bool:
        """Whether `module` belongs to a distribution this manifest governs."""
        return module.split(".")[0] in self._roots

    def is_public_module(self, module: str) -> bool:
        return module in self._exports

    def publishes(self, module: str, name: str) -> bool:
        """Whether `name` is a classified export of `module`, or a public submodule."""
        return name in self._exports.get(module, frozenset()) or self.is_public_module(
            f"{module}.{name}"
        )

    def reason_for_module(self, module: str) -> str | None:
        """Why importing `module` is unsupported, or None when it is supported."""
        if self.is_public_module(module):
            return None
        if any(part.startswith("_") for part in module.split(".")):
            return f"{module} is a private module"
        return f"{module} is not a classified public module"


def _statement(node: ast.stmt) -> str:
    """The import as written, recovered from the tree so fragments render too."""
    if isinstance(node, ast.Import):
        return "import " + ", ".join(
            alias.name + (f" as {alias.asname}" if alias.asname else "") for alias in node.names
        )
    assert isinstance(node, ast.ImportFrom)
    names = ", ".join(
        alias.name + (f" as {alias.asname}" if alias.asname else "") for alias in node.names
    )
    return f"from {'.' * node.level}{node.module or ''} import {names}"


def audit_tree(tree: ast.AST, surface: Surface, path: Path, line_offset: int) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not surface.owns(alias.name):
                    continue
                reason = surface.reason_for_module(alias.name)
                if reason is not None:
                    findings.append(
                        Finding(path, node.lineno + line_offset, _statement(node), reason)
                    )
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if not surface.owns(node.module):
                continue
            reason = surface.reason_for_module(node.module)
            if reason is not None:
                findings.append(Finding(path, node.lineno + line_offset, _statement(node), reason))
                continue
            unsupported = [
                alias.name
                for alias in node.names
                if alias.name != "*" and not surface.publishes(node.module, alias.name)
            ]
            star = any(alias.name == "*" for alias in node.names)
            if star:
                unsupported.append("*")
            if unsupported:
                detail = ", ".join(sorted(unsupported))
                findings.append(
                    Finding(
                        path,
                        node.lineno + line_offset,
                        _statement(node),
                        f"{node.module} does not classify: {detail}"
                        if not star
                        else f"a star import cannot be audited against {node.module}",
                    )
                )
    return findings


def _audit_lines(lines: list[str], surface: Surface, path: Path, line_offset: int) -> list[Finding]:
    """Recover imports from a block that does not parse as a whole module."""
    findings: list[Finding] = []
    for index, line in enumerate(lines, start=1):
        match = IMPORT_LINE.match(line)
        if match is None:
            continue
        fragment = line.strip().rstrip("\\").rstrip(",").rstrip("(").strip()
        try:
            tree = ast.parse(fragment)
        except SyntaxError:
            continue
        findings.extend(audit_tree(tree, surface, path, line_offset + index - 1))
    return findings


def audit_python(path: Path, surface: Surface) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - a file that cannot compile
        return [Finding(path, exc.lineno or 1, "<unparsable>", f"cannot be parsed: {exc.msg}")]
    return audit_tree(tree, surface, path, line_offset=0)


def audit_markdown(path: Path, surface: Surface) -> list[Finding]:
    """Audit the Python shown in fenced blocks, parsing each block on its own."""
    findings: list[Finding] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    block: list[str] | None = None
    start = 0
    for index, line in enumerate(lines, start=1):
        fence = FENCE.match(line)
        if fence is None:
            if block is not None:
                block.append(line)
            continue
        if block is None:
            if fence[1].lower() in PYTHON_FENCES:
                block, start = [], index
            continue
        try:
            tree = ast.parse("\n".join(block))
        except SyntaxError:
            findings.extend(_audit_lines(block, surface, path, line_offset=start))
        else:
            findings.extend(audit_tree(tree, surface, path, line_offset=start))
        block = None
    return findings


def audit_path(target: Path, surface: Surface) -> list[Finding]:
    """Audit one file, or every Python and Markdown file under a directory."""
    if target.is_file():
        candidates = [target]
    else:
        candidates = [
            path
            for path in sorted(target.rglob("*"))
            if path.is_file()
            and path.suffix in {".py", ".md"}
            and not any(part in {".git", ".venv", "__pycache__"} for part in path.parts)
        ]
    findings: list[Finding] = []
    for path in candidates:
        if path.suffix == ".py":
            findings.extend(audit_python(path, surface))
        elif path.suffix == ".md":
            findings.extend(audit_markdown(path, surface))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="files or directories to audit",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="public API manifest to audit against (default: docs/public-api.json)",
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    arguments = parser.parse_args(argv)

    try:
        surface = Surface.from_manifest(arguments.manifest)
    except (OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"public API manifest is unusable: {exc}", file=sys.stderr)
        return 2

    missing = [path for path in arguments.paths if not path.exists()]
    if missing:
        for path in missing:
            print(f"no such path: {path}", file=sys.stderr)
        return 2

    findings = [finding for path in arguments.paths for finding in audit_path(path, surface)]
    anchor = Path.cwd()
    if arguments.json:
        print(json.dumps({"findings": [f.as_dict(anchor) for f in findings]}, indent=2))
    elif findings:
        print(f"{len(findings)} import(s) outside the governed public API:")
        for finding in findings:
            print("  " + finding.render(anchor))
    else:
        print("every Agnara import is a governed public name")
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover - command line entry point
    raise SystemExit(main())
