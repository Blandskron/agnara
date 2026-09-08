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
from collections.abc import Callable
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
    ARCHITECTURES,
    EXPOSURES,
    MANIFEST_FILENAME,
    ProjectManifest,
    find_manifest,
    load_manifest,
)
from agnara_cli._minimal_template import minimal_app_files
from agnara_cli._names import validated_identifier

__all__ = ["add_app_alias_parsers", "add_app_parser", "run_app_create"]

#: Convenience alias -> the profile it fixes, from `docs/CLI_SPEC.md`
#: "Convenience aliases". That document lists exactly these four and warns
#: against adding scaffolding surface casually, so `core` and `full` have no
#: alias.
#:
#: `app-agent` maps to the `agentic` profile: the alias and the profile are
#: spelled differently on purpose, and only this table relates them.
ALIASES: dict[str, str] = {
    "app-api": "api",
    "app-mcp": "mcp",
    "app-agent": "agentic",
    "app-worker": "worker",
}

#: Architecture -> the template that generates it. `ARCHITECTURES` is the
#: manifest vocabulary and is deliberately wider: `docs/CLI_SPEC.md` calls
#: `vertical` a "potential future profile", so it is a name a manifest may
#: carry before a generator exists for it. Selecting one that is not here is
#: refused rather than quietly generating a different layout.
TEMPLATES: dict[str, Callable[[str, str, tuple[str, ...]], dict[str, str]]] = {
    "modular-hexagonal": app_files,
    "minimal": minimal_app_files,
}

#: Profile -> the exposures it starts an app with, in the order it scaffolds
#: them. The mapping is the table in `docs/CLI_SPEC.md` "Profiles".
#:
#: A profile is a scaffolding alias and nothing more (ADR 0013): it resolves to
#: exposures and then disappears, so no profile name is ever written to
#: `agnara.toml`. Recording one would make it look like a runtime app type,
#: which is exactly what ADR 0013 refuses.
PROFILES: dict[str, tuple[str, ...]] = {
    "core": (),
    "api": ("http",),
    "mcp": ("mcp",),
    "agentic": ("mcp", "a2a"),
    "worker": ("tasks", "events"),
    "full": ("http", "mcp", "a2a", "events", "tasks"),
}


def _add_create_arguments(parser: argparse.ArgumentParser, *, profile: str | None) -> None:
    """Define ``app create`` once, for the command and for every alias.

    `docs/CLI_SPEC.md` requires the aliases to "not create separate code paths",
    so they are not a second parser that happens to agree today -- they are this
    one, with ``profile`` fixed.

    When `profile` is given the parser does not offer ``--profile``: the alias
    *is* the profile, and exposing both would let a user write
    ``agnara app-mcp tools --profile worker``, a command that contradicts
    itself and whose answer would only ever be arbitrary.
    """
    parser.add_argument("name", help="the app name; a single lower-case Python identifier")
    parser.add_argument(
        "--architecture",
        # The manifest vocabulary, not just what is implemented: a reserved
        # name earns the explanation in `_resolved_architecture` rather than
        # argparse's "invalid choice", which reads like a typo.
        choices=sorted(ARCHITECTURES),
        help=(
            "the layout to generate. Defaults to the project's "
            "[defaults] architecture in agnara.toml."
        ),
    )
    if profile is None:
        parser.add_argument(
            "--profile",
            choices=sorted(PROFILES),
            help=(
                "start from a named set of exposures. Scaffolding only: the "
                "profile is not recorded, its exposures are. Defaults to core."
            ),
        )
    parser.add_argument(
        "--with",
        dest="exposures",
        metavar="a,b",
        help=(
            "comma-separated inbound adapters to scaffold: "
            + ", ".join(EXPOSURES)
            + ". Each adds one adapters/inbound/<name>.py."
        ),
    )
    parser.add_argument(
        "--project",
        metavar="DIR",
        help=(
            f"directory to search for {MANIFEST_FILENAME}; its ancestors are "
            "searched too. Defaults to the working directory."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be written and stop, creating nothing",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow replacing files that already exist",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the plan as deterministic JSON",
    )
    parser.set_defaults(handler=run_app_create, profile=profile)


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
            "Generate a bounded context and declare it in agnara.toml. "
            "Nothing is written until the whole plan is known. The command "
            "never prompts."
        ),
    )
    _add_create_arguments(create, profile=None)


def add_app_alias_parsers(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the convenience aliases from `docs/CLI_SPEC.md`.

    Each is ``agnara app create`` with one profile fixed. They exist for
    discoverability, and that document is explicit that they "MUST behave as
    aliases only", so they share `_add_create_arguments` and `run_app_create`
    rather than reimplementing either.
    """
    for alias, profile in ALIASES.items():
        parser = subparsers.add_parser(
            alias,
            help=f"shorthand for 'app create --profile {profile}'",
            description=(
                f"Exactly 'agnara app create NAME --profile {profile}'. Every "
                "other option of that command applies here unchanged."
            ),
        )
        _add_create_arguments(parser, profile=profile)


#: Identifiers the generated ``module.py`` already binds at module scope. The
#: app's own name becomes ``<name> = App("<name>")`` in that module, so an app
#: called ``app`` or ``register`` would generate code that shadows itself and
#: fails the moment the project imports it.
_RESERVED = frozenset(
    {
        "annotations",
        "app",
        "dependencies",
        "get_record",
        "list_records",
        "module",
        "provide_records",
        "provider",
        "register",
    }
)


def _validated_name(name: str) -> str:
    return validated_identifier(
        name,
        subject="app name",
        reserved=_RESERVED,
        reserved_because="the generated module already binds that name",
    )


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


def _declaration(name: str, project: str, architecture: str, exposures: tuple[str, ...]) -> str:
    """The manifest table this app adds, rendered deterministically."""
    listed = ", ".join(f'"{exposure}"' for exposure in exposures)
    return (
        f"\n[apps.{name}]\n"
        f'module = "{project}.apps.{name}"\n'
        f'path = "src/{project}/apps/{name}"\n'
        f'architecture = "{architecture}"\n'
        f"exposures = [{listed}]\n"
    )


def _updated_manifest(
    manifest: ProjectManifest,
    source: Path,
    name: str,
    architecture: str,
    exposures: tuple[str, ...],
) -> str:
    """Append one app table, preserving everything already in the file.

    Appending rather than re-serializing is deliberate: a manifest carries
    comments and an ordering its author chose, and a generator that rewrote it
    from a parsed model would delete both without saying so.
    """
    # Read without newline translation so the file keeps the line endings it
    # already has: rewriting a CRLF manifest as LF would change every line an
    # operator wrote, which is exactly what appending is meant to avoid.
    with source.open(encoding="utf-8", newline="") as handle:
        existing = handle.read()
    newline = "\r\n" if "\r\n" in existing else "\n"
    if not existing.endswith("\n"):
        existing += newline
    declaration = _declaration(name, manifest.name, architecture, exposures)
    return existing + declaration.replace("\n", newline)


def _resolved_architecture(requested: str | None, manifest: ProjectManifest, source: Path) -> str:
    """The architecture to generate, and to record for what was generated.

    An explicit ``--architecture`` wins; otherwise the project's declared
    default applies. Either way the result must name a template we have,
    because the manifest entry is a claim about the files on disk: writing one
    layout while declaring another is what makes ``agnara apps`` lie.
    """
    architecture = requested or manifest.default_architecture
    if architecture in TEMPLATES:
        return architecture

    available = ", ".join(sorted(TEMPLATES))
    if requested is None:
        raise GenerationError(
            f"{source}: [defaults] architecture is {architecture!r}, which has "
            f"no template yet. Choose one with --architecture ({available}), "
            "or change the project default."
        )
    raise GenerationError(
        f"architecture {architecture!r} is a reserved name with no generator "
        f"yet. Available: {available}."
    )


def _requested_exposures(requested: str | None) -> list[str]:
    """Parse ``--with``, rejecting a malformed list or an unknown exposure."""
    if requested is None:
        return []

    seen: list[str] = []
    for entry in requested.split(","):
        exposure = entry.strip()
        if not exposure:
            raise GenerationError(
                f"--with {requested!r} has an empty entry; list exposures as "
                "'http,mcp' with no trailing or repeated commas"
            )
        if exposure not in EXPOSURES:
            raise GenerationError(
                f"unknown exposure {exposure!r}. Available: {', '.join(EXPOSURES)}"
            )
        if exposure not in seen:
            seen.append(exposure)
    return seen


def _resolved_exposures(
    requested: str | None, profile: str | None, architecture: str
) -> tuple[str, ...]:
    """The inbound adapters to scaffold, and to record for what was scaffolded.

    A profile contributes its initial exposures and then disappears: ADR 0013
    makes profiles scaffolding aliases, not runtime app types, so nothing about
    the profile reaches the manifest. Only the result does.

    ``--with`` adds to a profile rather than replacing it. `docs/CLI_SPEC.md`
    permits either reading -- "combined/overridden" -- and ADR 0064 records why
    union wins.

    Order is the profile's exposures first, then anything ``--with`` adds that
    the profile did not already bring, with repeats dropped. A manifest should
    read back as the request that produced it.

    Raises:
        GenerationError: an empty entry, an unknown exposure, or any exposure
            at all on an architecture that has no adapters package.
    """
    seen = list(PROFILES[profile]) if profile is not None else []
    for exposure in _requested_exposures(requested):
        if exposure not in seen:
            seen.append(exposure)

    if seen and architecture != "modular-hexagonal":
        source = "--with" if profile is None else f"--profile {profile}"
        raise GenerationError(
            f"the {architecture} architecture has no adapters package, so it "
            f"cannot carry an inbound adapter for {', '.join(seen)}. Generate "
            f"this app with --architecture modular-hexagonal, or leave {source} off."
        )
    return tuple(seen)


def _plan(arguments: argparse.Namespace) -> tuple[GenerationPlan, ProjectManifest, str]:
    name = _validated_name(arguments.name)
    manifest, source = _manifest(arguments)
    if any(app.name == name for app in manifest.apps):
        raise GenerationError(
            f"{source}: app {name!r} is already declared. Remove it from the "
            "manifest first, or choose another name."
        )
    architecture = _resolved_architecture(
        getattr(arguments, "architecture", None), manifest, source
    )
    exposures = _resolved_exposures(
        getattr(arguments, "exposures", None),
        getattr(arguments, "profile", None),
        architecture,
    )

    root = source.parent
    files = TEMPLATES[architecture](manifest.name, name, exposures)
    files[MANIFEST_FILENAME] = _updated_manifest(manifest, source, name, architecture, exposures)
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

    apply_plan(plan, overwrite=arguments.overwrite)
    if arguments.json:
        return json.dumps(plan_json(plan), indent=2, sort_keys=True)
    written = "\n".join(f"{action.verb} {action.path}" for action in plan.actions)
    return written + "\n" + _next_steps(manifest.name, name)
