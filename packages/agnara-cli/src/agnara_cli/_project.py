"""``agnara project create``: the first generator.

`docs/CLI_SPEC.md` gives the command and its output tree. The generation
mechanics — plan, review, apply — live in `_generate`, so this module decides
*what* a project contains and not *how* a generator behaves. `agnara app
create` will reuse the same mechanism rather than reimplement the invariants.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agnara_cli._generate import (
    GenerationError,
    GenerationPlan,
    apply_plan,
    build_plan,
    plan_json,
    render_plan,
)
from agnara_cli._templates import project_files

__all__ = ["add_project_parser", "run_project_create"]


def add_project_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``project`` and its subcommands on the root parser."""
    parser = subparsers.add_parser(
        "project",
        help="create and manage Agnara projects",
        description="Project-level scaffolding.",
    )
    actions = parser.add_subparsers(dest="project_command", required=True, metavar="ACTION")
    create = actions.add_parser(
        "create",
        help="create a new Agnara project",
        description=(
            "Generate a project: a composition root, a manifest, a package "
            "layout and tests. Nothing is written until the whole plan is "
            "known, so a run that would replace a file refuses before it "
            "writes anything. The command never prompts."
        ),
    )
    create.add_argument("name", help="the project name; a single Python identifier")
    create.add_argument(
        "--directory",
        metavar="DIR",
        help="where to create the project directory. Defaults to the working directory.",
    )
    create.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be written and stop, creating nothing",
    )
    create.add_argument(
        "--overwrite",
        action="store_true",
        help="allow replacing files that already exist",
    )
    create.add_argument(
        "--json",
        action="store_true",
        help="emit the plan as deterministic JSON",
    )
    create.set_defaults(handler=run_project_create)


def _validated_name(name: str) -> str:
    """Refuse a name that could not become a package, an app or a manifest.

    The rule is the manifest's rule: a project name is a Python identifier,
    because it becomes a package directory, an import path and the value of
    ``[project] name``. Checking it here means a bad name fails before any
    directory is created rather than producing a project that will not load.
    """
    if not name.isidentifier():
        raise GenerationError(
            f"invalid project name {name!r}: it becomes a package and an import "
            "path, so it must be a single Python identifier"
        )
    if name != name.lower():
        raise GenerationError(
            f"invalid project name {name!r}: use lower_case, so the package name "
            "matches the import path on case-insensitive filesystems"
        )
    return name


def _plan(arguments: argparse.Namespace) -> GenerationPlan:
    name = _validated_name(arguments.name)
    parent = Path(arguments.directory) if arguments.directory else Path.cwd()
    if arguments.directory and not parent.is_dir():
        raise GenerationError(f"{parent}: is not a directory")
    root = parent / name
    if root.exists() and not root.is_dir():
        raise GenerationError(f"{root}: exists and is not a directory")
    return build_plan(root, project_files(name))


def run_project_create(arguments: argparse.Namespace) -> str:
    """Plan the project, then write it unless this is a dry run."""
    plan = _plan(arguments)
    if arguments.dry_run:
        if arguments.json:
            return json.dumps(plan_json(plan), indent=2, sort_keys=True)
        return render_plan(plan)

    apply_plan(plan, overwrite=arguments.overwrite)
    if arguments.json:
        return json.dumps(plan_json(plan), indent=2, sort_keys=True)
    written = "\n".join(f"{action.verb} {plan.root.name}/{action.path}" for action in plan.actions)
    return (
        f"{written}\n\n"
        f"Created {plan.root.name}. Next:\n"
        f"  cd {plan.root.name}\n"
        f"  uv sync\n"
        f"  uv run pytest"
    )
