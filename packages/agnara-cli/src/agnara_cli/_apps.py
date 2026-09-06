"""``agnara apps``: list what the project manifest declares.

`docs/CLI_SPEC.md` specifies this command as "Lists apps, architecture and
exposures", which is exactly the data `agnara.toml` holds. It reads the
manifest and nothing else: no module is imported and no project code runs, so
this answers what a project *declares*, not what a composed application
registers. Those can diverge, and saying so is more useful than pretending the
manifest is runtime truth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agnara_cli._manifest import (
    MANIFEST_FILENAME,
    ManifestError,
    ProjectManifest,
    find_manifest,
    load_manifest,
)

__all__ = ["add_apps_parser", "run_apps"]

#: The declared JSON shape, so a consumer can detect a change rather than
#: discover one. Bumped when a field's meaning changes, not when one is added.
FORMAT_VERSION = 1


def add_apps_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``apps`` and its arguments on the root parser."""
    parser = subparsers.add_parser(
        "apps",
        help="list the apps a project manifest declares",
        description=(
            f"Read {MANIFEST_FILENAME} and list each declared app with its "
            "architecture and exposures. Nothing is imported and no project "
            "code runs, so this reports declared composition intent rather "
            "than what a compiled application registers."
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
        "--json",
        action="store_true",
        help="emit the declaration as deterministic JSON",
    )
    parser.set_defaults(handler=run_apps)


def _manifest(arguments: argparse.Namespace) -> ProjectManifest:
    start = Path(arguments.project) if arguments.project else Path.cwd()
    if arguments.project and not start.is_dir():
        raise ManifestError(f"{start}: is not a directory")
    found = find_manifest(start)
    if found is None:
        raise ManifestError(
            f"no {MANIFEST_FILENAME} found in {start.resolve()} or any parent directory"
        )
    return load_manifest(found)


def _json_data(manifest: ProjectManifest) -> dict[str, object]:
    return {
        "format_version": FORMAT_VERSION,
        "project": {
            "name": manifest.name,
            "python": manifest.python,
            "default_architecture": manifest.default_architecture,
        },
        "apps": [
            {
                "name": app.name,
                "module": app.module,
                "path": str(app.path),
                "architecture": app.architecture,
                "exposures": list(app.exposures),
            }
            for app in manifest.apps
        ],
    }


def _text(manifest: ProjectManifest) -> str:
    lines = [f"project {manifest.name}"]
    if manifest.python is not None:
        lines.append(f"  python {manifest.python}")
    lines.append(f"  default architecture {manifest.default_architecture}")
    if not manifest.apps:
        lines.append("")
        lines.append("no apps declared")
        return "\n".join(lines)

    width = max(len(app.name) for app in manifest.apps)
    lines.append("")
    for app in manifest.apps:
        exposures = ", ".join(app.exposures) if app.exposures else "none"
        lines.append(f"{app.name.ljust(width)}  {app.architecture}  exposures: {exposures}")
        lines.append(f"{' ' * width}  {app.module}  ({app.path})")
    return "\n".join(lines)


def run_apps(arguments: argparse.Namespace) -> str:
    """Read the manifest and render it. Returns the text to print."""
    manifest = _manifest(arguments)
    if arguments.json:
        return json.dumps(_json_data(manifest), indent=2, sort_keys=True)
    return _text(manifest)
