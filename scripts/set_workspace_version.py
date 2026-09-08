"""Move every first-party distribution to one development or release version.

The version identity is a workspace invariant, not a collection of unrelated
edits.  This command validates the whole workspace before writing anything,
updates every project and adapter core pin, and rolls those edits back if the
lockfile cannot be refreshed.

Examples::

    python scripts/set_workspace_version.py development 0.1.0a4
    python scripts/set_workspace_version.py release 0.1.0a4
    python scripts/set_workspace_version.py development 0.1.0a4 --check

Only the standard library is imported so the command remains usable while the
development environment itself is being repaired.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = "agnara"
STATUS_RELATIVE = Path("docs/releases/release-status.json")
LOCK_RELATIVE = Path("uv.lock")

TARGET_PATTERN = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:(?:a|b|rc)(?:0|[1-9]\d*))?"
)
VERSION_LINE = re.compile(r'(?m)^version = "([^"]+)"$')
CORE_REQUIREMENT = re.compile(r'"agnara(?:==[^"]+)?"')


class TransitionError(Exception):
    """The requested transition is unsafe or could not be completed."""


@dataclass(frozen=True, slots=True)
class Package:
    path: Path
    name: str
    version: str
    core_requirements: tuple[str, ...]
    text: str


@dataclass(frozen=True, slots=True)
class Plan:
    mode: str
    target: str
    version: str
    files: tuple[tuple[Path, str], ...]


def _target_version(mode: str, target: str) -> str:
    if TARGET_PATTERN.fullmatch(target) is None or target == "0.0.0":
        raise TransitionError(
            f"target {target!r} must be a non-sentinel public PEP 440 release version"
        )
    return f"{target}.dev0" if mode == "development" else target


def _load_current_target(workspace: Path) -> str:
    import json

    path = workspace / STATUS_RELATIVE
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        target = document["current_target"]
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        raise TransitionError(f"cannot read current release target from {path}: {exc}") from exc
    if not isinstance(target, str):
        raise TransitionError(f"current_target in {path} must be a string")
    return target


def _load_packages(workspace: Path) -> list[Package]:
    paths = sorted((workspace / "packages").glob("*/pyproject.toml"))
    if not paths:
        raise TransitionError("no first-party package metadata found")

    packages: list[Package] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
            project = tomllib.loads(text)["project"]
            name = project["name"]
            version = project["version"]
            dependencies = project.get("dependencies", [])
        except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError) as exc:
            raise TransitionError(f"cannot read project metadata from {path}: {exc}") from exc
        if not isinstance(name, str) or not isinstance(version, str):
            raise TransitionError(f"{path}: project name and version must be strings")
        if not isinstance(dependencies, list) or not all(
            isinstance(requirement, str) for requirement in dependencies
        ):
            raise TransitionError(f"{path}: project dependencies must be strings")
        core_requirements = tuple(
            requirement
            for requirement in dependencies
            if requirement == CORE or requirement.startswith(f"{CORE}==")
        )
        packages.append(Package(path, name, version, core_requirements, text))

    names = [package.name for package in packages]
    if len(names) != len(set(names)):
        raise TransitionError("first-party distribution names must be unique")
    if names.count(CORE) != 1:
        raise TransitionError(f"workspace must contain exactly one {CORE!r} distribution")
    return packages


def _validate_current(packages: list[Package]) -> None:
    versions = {package.version for package in packages}
    if len(versions) != 1:
        detail = ", ".join(f"{package.name}={package.version}" for package in packages)
        raise TransitionError(f"refusing a partially versioned workspace: {detail}")

    requirements: set[str] = set()
    for package in packages:
        if package.name == CORE:
            if package.core_requirements:
                raise TransitionError(f"{CORE} must not depend on itself")
            continue
        if len(package.core_requirements) != 1:
            raise TransitionError(
                f"{package.name} must declare exactly one dependency on {CORE}; "
                f"found {list(package.core_requirements)}"
            )
        requirements.add(package.core_requirements[0])

    current = next(iter(versions))
    permitted = {CORE, f"{CORE}=={current}"}
    if len(requirements) != 1 or not requirements <= permitted:
        raise TransitionError(
            "refusing partially synchronized core requirements: " + ", ".join(sorted(requirements))
        )


def plan_transition(workspace: Path, mode: str, target: str) -> Plan:
    """Validate the complete workspace and render every changed package file."""
    desired = _target_version(mode, target)
    current_target = _load_current_target(workspace)
    if target != current_target:
        raise TransitionError(
            f"requested target {target} does not match release-status "
            f"current_target {current_target}"
        )

    packages = _load_packages(workspace)
    _validate_current(packages)
    rendered: list[tuple[Path, str]] = []
    for package in packages:
        if len(VERSION_LINE.findall(package.text)) != 1:
            raise TransitionError(f"{package.path}: expected exactly one project version line")
        text = VERSION_LINE.sub(f'version = "{desired}"', package.text, count=1)
        if package.name != CORE:
            matches = CORE_REQUIREMENT.findall(text)
            if len(matches) != 1:
                raise TransitionError(
                    f"{package.path}: expected exactly one editable core "
                    f"requirement, found {matches}"
                )
            text = CORE_REQUIREMENT.sub(f'"{CORE}=={desired}"', text, count=1)
        rendered.append((package.path, text))
    return Plan(mode, target, desired, tuple(rendered))


def _write_atomic(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def _run_uv(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["uv", "lock", *arguments],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise TransitionError(f"cannot run uv lock: {exc}") from exc


def execute(plan: Plan, workspace: Path, *, check: bool) -> tuple[Path, ...]:
    lock = workspace / LOCK_RELATIVE
    expected = dict(plan.files)
    if check:
        mismatches = [path for path, text in plan.files if path.read_text(encoding="utf-8") != text]
        if mismatches:
            shown = ", ".join(str(path.relative_to(workspace)) for path in mismatches)
            raise TransitionError(f"workspace is not in {plan.mode} state {plan.version}: {shown}")
        result = _run_uv(workspace, "--check")
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise TransitionError(f"uv lock --check failed: {detail}")
        return (*expected, lock)

    originals = {path: path.read_bytes() for path in expected}
    lock_existed = lock.is_file()
    lock_original = lock.read_bytes() if lock_existed else b""
    changed = tuple(path for path, text in plan.files if originals[path] != text.encode())
    try:
        for path in changed:
            _write_atomic(path, expected[path].encode())
        result = _run_uv(workspace)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise TransitionError(f"uv lock failed: {detail}")
    except BaseException:
        for path, content in originals.items():
            _write_atomic(path, content)
        if lock_existed:
            _write_atomic(lock, lock_original)
        elif lock.exists():
            lock.unlink()
        raise
    return (*changed, lock)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("development", "release"))
    parser.add_argument("target", help="public target without a .dev or local suffix")
    parser.add_argument("--check", action="store_true", help="verify without changing files")
    parser.add_argument("--workspace", type=Path, default=ROOT, help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)

    workspace = arguments.workspace.resolve()
    try:
        plan = plan_transition(workspace, arguments.mode, arguments.target)
        paths = execute(plan, workspace, check=arguments.check)
    except TransitionError as exc:
        print(f"version transition refused: {exc}", file=sys.stderr)
        return 1

    verb = "checked" if arguments.check else "updated"
    print(f"{verb} workspace {arguments.mode} version {plan.version}")
    for path in paths:
        print(f"- {path.relative_to(workspace)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
