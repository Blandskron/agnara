"""Read and validate ``agnara.toml``, the project composition manifest.

`docs/PROJECT_MANIFEST.md` proposes this file as an explicit, machine-readable
description of what a project contains. It describes composition *intent*:
which apps exist, how each is laid out, and which exposures each was scaffolded
with. Python composition remains the runtime truth, so nothing here is loaded,
imported or executed — reading a manifest runs no project code.

Validation is strict on purpose. An unknown table or key is rejected rather
than ignored, because a typo that silently disables an app is worse to debug
than a manifest that refuses to load. See ADR 0059.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = [
    "ARCHITECTURES",
    "DEFAULT_ARCHITECTURE",
    "EXPOSURES",
    "MANIFEST_FILENAME",
    "ManifestApp",
    "ManifestError",
    "ProjectManifest",
    "find_manifest",
    "load_manifest",
    "parse_manifest",
]

MANIFEST_FILENAME = "agnara.toml"

#: Layouts `docs/CLI_SPEC.md` names. A manifest may not declare one this CLI
#: cannot generate, because the value drives scaffolding rather than describing
#: an opinion.
ARCHITECTURES = ("modular-hexagonal", "minimal", "vertical")
DEFAULT_ARCHITECTURE = "modular-hexagonal"

#: Exposure kinds `docs/CLI_SPEC.md` names for `--with` and `app expose`.
EXPOSURES = ("http", "mcp", "a2a", "tasks", "events")


class ManifestError(Exception):
    """A manifest is missing, unreadable or invalid.

    Carries a caller-facing diagnostic naming the file and the offending key
    path. The CLI prints it as one line; an operator or an agent should be able
    to act on it without reading a traceback.
    """


@dataclass(frozen=True, slots=True)
class ManifestApp:
    """One declared app: where its code lives and what it was exposed with."""

    name: str
    module: str
    path: PurePosixPath
    architecture: str
    exposures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    """One project's declared composition, in declaration order."""

    name: str
    python: str | None
    default_architecture: str
    apps: tuple[ManifestApp, ...]
    source: Path | None = None

    def app(self, name: str) -> ManifestApp:
        """Return one declared app, or explain which names exist."""
        for app in self.apps:
            if app.name == name:
                return app
        known = ", ".join(declared.name for declared in self.apps) or "none"
        raise ManifestError(f"no app named {name!r} is declared; declared apps: {known}")


def _where(source: Path | None) -> str:
    return str(source) if source is not None else MANIFEST_FILENAME


def _fail(source: Path | None, key: str, problem: str) -> ManifestError:
    return ManifestError(f"{_where(source)}: {key}: {problem}")


def _table(value: object, source: Path | None, key: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise _fail(source, key, f"must be a table, not {type(value).__name__}")
    return value


def _reject_unknown(
    table: Mapping[str, Any],
    known: Iterable[str],
    source: Path | None,
    key: str,
) -> None:
    """Refuse a key this format does not define.

    Ignoring one would let ``exposure = ["http"]`` sit next to a working
    manifest and do nothing at all, which is the failure mode this rule exists
    to prevent. ADR 0059 records the cost: a manifest written for a newer
    Agnara is rejected by an older one.
    """
    unknown = sorted(set(table) - set(known))
    if unknown:
        accepted = ", ".join(sorted(known))
        raise _fail(
            source,
            key,
            f"unknown key(s) {', '.join(repr(name) for name in unknown)}; accepted: {accepted}",
        )


def _required_string(
    table: Mapping[str, Any],
    field: str,
    source: Path | None,
    key: str,
) -> str:
    if field not in table:
        raise _fail(source, f"{key}.{field}", "is required")
    value = table[field]
    if not isinstance(value, str) or not value.strip():
        raise _fail(source, f"{key}.{field}", "must be a non-empty string")
    return value.strip()


def _optional_string(
    table: Mapping[str, Any],
    field: str,
    source: Path | None,
    key: str,
) -> str | None:
    if field not in table:
        return None
    value = table[field]
    if not isinstance(value, str) or not value.strip():
        raise _fail(source, f"{key}.{field}", "must be a non-empty string when present")
    return value.strip()


def _choice(
    value: str,
    allowed: tuple[str, ...],
    source: Path | None,
    key: str,
) -> str:
    if value not in allowed:
        raise _fail(source, key, f"{value!r} is not one of: {', '.join(allowed)}")
    return value


def _module_path(value: str, source: Path | None, key: str) -> str:
    for segment in value.split("."):
        if not segment.isidentifier():
            raise _fail(source, key, f"{value!r} is not a module path")
    return value


def _app_path(value: str, source: Path | None, key: str) -> PurePosixPath:
    """Validate a project-relative location a generator will later write to.

    An absolute path or one climbing out of the project would let a manifest
    aim a future generator at somewhere it was never invited. Reading is
    harmless; validating containment here is what makes writing safe later.
    """
    if "\\" in value:
        raise _fail(source, key, f"{value!r} must use '/' separators, so it is portable")
    candidate = PurePosixPath(value)
    if candidate.is_absolute():
        raise _fail(source, key, f"{value!r} must be relative to the project directory")
    parts = candidate.parts
    if not parts:
        raise _fail(source, key, "must not be empty")
    if any(part == ".." for part in parts):
        raise _fail(source, key, f"{value!r} must not leave the project directory")
    return candidate


def _exposures(value: object, source: Path | None, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _fail(source, key, f"must be an array, not {type(value).__name__}")
    seen: list[str] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, str):
            raise _fail(source, f"{key}[{index}]", f"must be a string, not {type(entry).__name__}")
        exposure = _choice(entry, EXPOSURES, source, f"{key}[{index}]")
        if exposure in seen:
            raise _fail(source, f"{key}[{index}]", f"{exposure!r} is listed more than once")
        seen.append(exposure)
    return tuple(seen)


def _app(
    name: str,
    table: Mapping[str, Any],
    default_architecture: str,
    source: Path | None,
) -> ManifestApp:
    key = f"apps.{name}"
    if not name.isidentifier():
        raise _fail(source, key, f"{name!r} is not a valid app name")
    _reject_unknown(table, ("module", "path", "architecture", "exposures"), source, key)
    module = _module_path(_required_string(table, "module", source, key), source, f"{key}.module")
    path = _app_path(_required_string(table, "path", source, key), source, f"{key}.path")
    declared = _optional_string(table, "architecture", source, key)
    architecture = (
        default_architecture
        if declared is None
        else _choice(declared, ARCHITECTURES, source, f"{key}.architecture")
    )
    exposures = (
        ()
        if "exposures" not in table
        else _exposures(table["exposures"], source, f"{key}.exposures")
    )
    return ManifestApp(
        name=name,
        module=module,
        path=path,
        architecture=architecture,
        exposures=exposures,
    )


def parse_manifest(text: str, *, source: Path | None = None) -> ProjectManifest:
    """Validate manifest text and return the declared composition.

    ``source`` only names the file in diagnostics; nothing is read from disk.
    """
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(f"{_where(source)}: is not valid TOML: {error}") from error

    _reject_unknown(document, ("project", "defaults", "apps"), source, "<root>")
    if "project" not in document:
        raise _fail(source, "project", "table is required")

    project = _table(document["project"], source, "project")
    _reject_unknown(project, ("name", "python"), source, "project")
    name = _required_string(project, "name", source, "project")
    if not name.isidentifier():
        raise _fail(source, "project.name", f"{name!r} is not a valid project name")
    # Deliberately not parsed: a PEP 440 specifier needs a dependency the CLI
    # does not have. ADR 0059 records that limit rather than implying a check.
    python = _optional_string(project, "python", source, "project")

    default_architecture = DEFAULT_ARCHITECTURE
    if "defaults" in document:
        defaults = _table(document["defaults"], source, "defaults")
        _reject_unknown(defaults, ("architecture",), source, "defaults")
        declared = _optional_string(defaults, "architecture", source, "defaults")
        if declared is not None:
            default_architecture = _choice(declared, ARCHITECTURES, source, "defaults.architecture")

    apps: list[ManifestApp] = []
    if "apps" in document:
        for app_name, app_table in _table(document["apps"], source, "apps").items():
            apps.append(
                _app(
                    app_name,
                    _table(app_table, source, f"apps.{app_name}"),
                    default_architecture,
                    source,
                )
            )

    for field in ("module", "path"):
        seen: dict[object, str] = {}
        for app in apps:
            value = getattr(app, field)
            if value in seen:
                raise _fail(
                    source,
                    f"apps.{app.name}.{field}",
                    f"{str(value)!r} is already declared by app {seen[value]!r}",
                )
            seen[value] = app.name

    return ProjectManifest(
        name=name,
        python=python,
        default_architecture=default_architecture,
        apps=tuple(apps),
        source=source,
    )


def load_manifest(path: Path) -> ProjectManifest:
    """Read and validate one manifest file."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ManifestError(f"{path}: no such file") from error
    except OSError as error:
        raise ManifestError(f"{path}: cannot be read: {error}") from error
    except UnicodeDecodeError as error:
        raise ManifestError(f"{path}: is not valid UTF-8: {error}") from error
    return parse_manifest(text, source=path)


def find_manifest(start: Path | None = None) -> Path | None:
    """Search ``start`` and its ancestors for ``agnara.toml``.

    Returns the first one found, or ``None``. Not finding a manifest is a
    normal answer — a project may not have one yet — so the caller decides
    whether that is an error.
    """
    current = (Path.cwd() if start is None else Path(start)).resolve()
    for directory in (current, *current.parents):
        candidate = directory / MANIFEST_FILENAME
        if candidate.is_file():
            return candidate
    return None
