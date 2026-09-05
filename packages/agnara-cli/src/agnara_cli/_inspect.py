"""``agnara inspect``: one snapshot, one visibility decision, two renderings.

`docs/CLI_SPEC.md` requires that the text and ``--json`` modes consume the
same filtered protocol-neutral snapshot. They do, literally: both take the
view `_view` builds and differ only in the last call.

Offline inspection is not a bypass. The visibility decision is a command-line
argument, and ``--json`` output is a document the operator may go on to
publish, so the same fields can be withheld here as anywhere else.
"""

from __future__ import annotations

import argparse
import json

from agnara_cli._render import render_snapshot
from agnara_cli._view import add_view_arguments, resolve_view

__all__ = ["add_inspect_parser", "run_inspect"]


def add_inspect_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``inspect`` and its arguments on the root parser."""
    parser = subparsers.add_parser(
        "inspect",
        help="show a compiled application's capabilities",
        description=(
            "Import a compiled Agnara application and present its filtered "
            "protocol-neutral introspection snapshot. Importing the target "
            "executes the module that defines it."
        ),
    )
    add_view_arguments(parser)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the versioned snapshot as deterministic JSON",
    )
    parser.set_defaults(handler=run_inspect)


def run_inspect(arguments: argparse.Namespace) -> str:
    """Resolve, describe, filter and render. Returns the text to print."""
    view = resolve_view(arguments)
    if arguments.json:
        return json.dumps(view.snapshot.json_data(), indent=2, sort_keys=True)
    return render_snapshot(view.snapshot, view.visibility)
