"""The ``agnara`` command's entry point and its exit-code contract.

`docs/CLI_SPEC.md` requires machine output to have defined exit codes and no
ANSI decoration, so both are decided here rather than per command.

Exit codes:

``0``
    the command produced its answer, even when that answer is "nothing is
    visible" or nothing at all, as when a document was written to a file
``1``
    the operator's input or application could not be used, reported as a
    diagnostic on stderr rather than a traceback
``2``
    argparse rejected the command line
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from agnara_cli._apps import add_apps_parser
from agnara_cli._context import add_context_parser
from agnara_cli._generate import GenerationError
from agnara_cli._graph import add_graph_parser
from agnara_cli._inspect import add_inspect_parser
from agnara_cli._manifest import ManifestError
from agnara_cli._project import add_project_parser
from agnara_cli._schema import add_schema_parser
from agnara_cli._target import TargetError

__all__ = ["main"]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def _version() -> str:
    try:
        return version("agnara-cli")
    except PackageNotFoundError:  # pragma: no cover - only outside an install
        return "unknown"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agnara",
        description="Agnara project introspection and scaffolding.",
    )
    parser.add_argument("--version", action="version", version=f"agnara {_version()}")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    add_apps_parser(subparsers)
    add_inspect_parser(subparsers)
    add_graph_parser(subparsers)
    add_project_parser(subparsers)
    add_schema_parser(subparsers)
    add_context_parser(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return its exit code.

    A `TargetError` is the operator's problem — a bad target, a module that
    will not import, an application that will not compile — and so are a
    `ManifestError`, a missing or invalid `agnara.toml`, and a
    `GenerationError`, a generator refusing to write. All are reported as
    one line on stderr. Anything else is a defect in this CLI and is left to
    propagate, because hiding it would make it unreportable.
    """
    arguments = _parser().parse_args(argv)
    try:
        output = arguments.handler(arguments)
    except (GenerationError, ManifestError, TargetError) as error:
        print(f"agnara: {error}", file=sys.stderr)
        return EXIT_FAILED
    _emit(output)
    return EXIT_OK


def _emit(output: str | bytes | None) -> None:
    """Write a command's answer, or nothing when it produced none.

    Bytes go to the buffer unchanged. A document another surface already
    serialized must reach a pipe exactly as that surface would send it, and
    encoding it through the text layer would let the platform's newline
    translation rewrite it.
    """
    if output is None:
        return
    if isinstance(output, bytes):
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
        return
    print(output)
