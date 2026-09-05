"""``agnara app create``: the second generator, and the one that proves the first.

It reuses `_generate` unchanged apart from one addition the first generator did
not need: declaring that a file is *meant* to be rewritten, so adding a table to
``agnara.toml`` is an update rather than a conflict with itself.

The manifest edit appends to the existing text instead of re-serializing it.
Re-serializing would silently discard comments and ordering an operator wrote,
which AGENTS.md's "update project metadata safely" and "never silently delete
modified files" both rule out. See ADR 0061.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agnara_cli._app_template import app_files
from agnara_cli._generate import (
    GenerationError,
    GenerationPlan,
    apply_plan,
    build_plan,
    plan_json,
    render_plan,
)
from agnara_cli._manifest import (
    MANIFEST_FILENAME,
    ManifestError,
    ProjectManifest,
    find_manifest,
    load_manifest,
)

__all__ = ["add_app_parser", "run_app_create"]


def add_app_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``app`` and its subcommands on the root parser."""
    parser = subparsers.add_parser(
        "app",
        help="create and manage apps inside a project",
        description="App-level scaffolding. An app is one bounded context.",
    )
    actions = parser.add_subparsers(dest="app_command", required=True, metavar="ACTION")
    create = actions.add_parser(
        "create",
        help="create an app in the current project",
        description=(
            "Generate a bounded context in the modular-hexagonal layout and "
            "declare it in agnara.toml. Nothing is written until the whole "
            "plan is known. The command never prompts."
        ),
    )
    create.add_argument("name", help="the app name; a single lower-case Python identifier")
    create.add_argument(
        "--project",
        metavar="DIR",
        help=(
            f"directory to search for {MANIFEST_FILENAME}; its ancestors are "
            "searched too. Defaults to the working directory."
        ),
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
    create.set_defaults(handler=run_app_create)


def _validated_name(name: str) -> str:
    if not name.isidentifier():
        raise GenerationError(
            f"invalid app name {name!r}: it becomes a package and a manifest "
            "key, so it must be a single Python identifier"
        )
    if name != name.lower():
        raise GenerationError(
            f"invalid app name {name!r}: use lower_case, so the package name "
            "matches the import path on case-insensitive filesystems"
        )
    return name


def _manifest(arguments: argparse.Namespace) -> tuple[ProjectManifest, Path]:
    start = Path(arguments.project) if arguments.project else Path.cwd()
    if arguments.project and not start.is_dir():
        raise GenerationError(f"{start}: is not a directory")
    found = find_manifest(start)
    if found is None:
        raise GenerationError(
            f"no {MANIFEST_FILENAME} found in {start.resolve()} or any parent "
            "directory. Create a project first with 'agnara project create'."
        )
    return load_manifest(found), found


def _declaration(name: str, project: str, architecture: str) -> str:
    """The manifest table this app adds, rendered deterministically."""
    return (
        f"\n[apps.{name}]\n"
        f'module = "{project}.apps.{name}"\n'
        f'path = "src/{project}/apps/{name}"\n'
        f'architecture = "{architecture}"\n'
        "exposures = []\n"
    )


def _updated_manifest(manifest: ProjectManifest, source: Path, name: str) -> str:
    """Append one app table, preserving everything already in the file.

    Appending rather than re-serializing is deliberate: a manifest carries
    comments and an ordering its author chose, and a generator that rewrote it
    from a parsed model would delete both without saying so.
    """
    existing = source.read_text(encoding="utf-8")
    if not existing.endswith("\n"):
        existing += "\n"
    return existing + _declaration(name, manifest.name, manifest.default_architecture)


def _plan(arguments: argparse.Namespace) -> tuple[GenerationPlan, ProjectManifest, str]:
    name = _validated_name(arguments.name)
    manifest, source = _manifest(arguments)
    if any(app.name == name for app in manifest.apps):
        raise GenerationError(
            f"{source}: app {name!r} is already declared. Remove it from the "
            "manifest first, or choose another name."
        )

    root = source.parent
    files = app_files(manifest.name, name)
    files[MANIFEST_FILENAME] = _updated_manifest(manifest, source, name)
    plan = build_plan(root, files, updates=(MANIFEST_FILENAME,))
    return plan, manifest, name


def _next_steps(project: str, name: str) -> str:
    return (
        f"\nDeclared {name} in {MANIFEST_FILENAME}. Wire it into the composition "
        f"root, src/{project}/bootstrap.py:\n\n"
        f"    from {project}.apps.{name} import module as {name}_module\n\n"
        f"    {name}_module.register(app, dependencies)\n"
    )


def run_app_create(arguments: argparse.Namespace) -> str:
    """Plan the app, then write it unless this is a dry run."""
    plan, manifest, name = _plan(arguments)
    if arguments.dry_run:
        if arguments.json:
            return json.dumps(plan_json(plan), indent=2, sort_keys=True)
        return render_plan(plan)

    try:
        apply_plan(plan, overwrite=arguments.overwrite)
    except ManifestError as error:  # pragma: no cover - defensive
        raise GenerationError(str(error)) from error
    if arguments.json:
        return json.dumps(plan_json(plan), indent=2, sort_keys=True)
    written = "\n".join(f"{action.verb} {action.path}" for action in plan.actions)
    return written + "\n" + _next_steps(manifest.name, name)
