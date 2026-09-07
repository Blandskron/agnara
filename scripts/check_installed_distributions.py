"""Assert every first-party distribution is usable once installed.

The packaging gate used to build seven distributions and install one. Building
a wheel proves it can be produced; it does not prove an installer can resolve
its dependencies, or that the package it contains imports from where it was
installed to. Those are different claims, and only the second is what a user
experiences.

This script makes the second claim checkable. It runs inside an environment
that holds nothing but the built wheels, so it imports **only the standard
library** -- adding a third-party import here would make the gate depend on a
package the gate exists to validate.

Expected distributions are discovered from the workspace layout rather than
listed, so adding a distribution extends this check instead of escaping it.

    python scripts/check_installed_distributions.py --workspace <checkout> \
        --require-installed

``--require-installed`` additionally asserts that nothing resolved from the
workspace source tree. It is off by default because the development
environment installs the workspace packages from ``packages/*/src``, where
importing from the source tree is correct rather than a defect.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.resources
import os
from dataclasses import dataclass
from pathlib import Path

#: `packages/<distribution>/src/<import name>/__init__.py`, the layout
#: `tests/architecture/test_workspace_layout.py` enforces and ADR 0017 fixes.
SRC_LAYOUT = "src"


@dataclass(frozen=True, slots=True)
class Distribution:
    """One first-party distribution and the package it installs."""

    name: str
    import_name: str


def discover(workspace: Path) -> tuple[list[Distribution], list[str]]:
    """Every distribution the workspace defines, read from the directory layout."""
    packages_dir = workspace / "packages"
    if not packages_dir.is_dir():
        return [], [f"no packages directory under {workspace}"]

    found: list[Distribution] = []
    problems: list[str] = []
    for package in sorted(packages_dir.iterdir()):
        if not package.is_dir():
            continue
        source = package / SRC_LAYOUT
        modules = (
            sorted(child for child in source.iterdir() if (child / "__init__.py").is_file())
            if source.is_dir()
            else []
        )
        if len(modules) != 1:
            # Ambiguity here would make the gate check the wrong thing, which
            # is worse than not checking: report it rather than guessing.
            problems.append(
                f"{package.name}: expected exactly one importable package under "
                f"{SRC_LAYOUT}/, found {[module.name for module in modules]}"
            )
            continue
        found.append(Distribution(name=package.name, import_name=modules[0].name))

    if not found and not problems:
        problems.append(f"no distributions found under {packages_dir}")
    return found, problems


def check_import(
    distribution: Distribution,
    *,
    workspace: Path,
    require_installed: bool,
) -> list[str]:
    """Import the package and report what is wrong with where it came from."""
    problems: list[str] = []
    try:
        module = importlib.import_module(distribution.import_name)
    except ImportError as exc:
        return [f"{distribution.name}: cannot import {distribution.import_name}: {exc}"]

    origin = getattr(module, "__file__", None)
    if origin is None:
        return [f"{distribution.name}: {distribution.import_name} has no __file__"]
    resolved = Path(os.path.realpath(origin))

    if require_installed:
        if "site-packages" not in resolved.parts:
            problems.append(
                f"{distribution.name}: imported from {resolved}, which is not an installed location"
            )
        # A wheel that failed to install still imports when the checkout is on
        # sys.path. That is the failure this gate exists to catch.
        if resolved.is_relative_to(os.path.realpath(workspace)):
            problems.append(f"{distribution.name}: imported from the checkout at {resolved}")
    return problems


def data_files(workspace: Path, distribution: Distribution) -> list[str]:
    """Every non-Python file the source package ships, as posix relative paths.

    Discovered rather than listed: `py.typed` decides whether the shipped
    annotations are honoured at all (PEP 561), and `agnara-http` serves its
    vendored documentation UIs out of the installed package. Both are invisible
    to an import check, and both are the kind of thing a packaging change drops
    silently.
    """
    root = workspace / "packages" / distribution.name / SRC_LAYOUT / distribution.import_name
    if not root.is_dir():
        return []
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.suffix != ".py" and "__pycache__" not in path.parts
    )


def check_package_data(
    distribution: Distribution,
    *,
    workspace: Path,
) -> list[str]:
    """Every data file in the source package resolves inside the installed one."""
    expected = data_files(workspace, distribution)
    if not expected:
        return []
    try:
        root = importlib.resources.files(distribution.import_name)
    except (ImportError, TypeError) as exc:
        return [f"{distribution.name}: cannot resolve package resources: {exc}"]

    missing = [
        relative for relative in expected if not root.joinpath(*relative.split("/")).is_file()
    ]
    if not missing:
        return []
    shown = ", ".join(missing[:5]) + ("..." if len(missing) > 5 else "")
    return [
        f"{distribution.name}: {len(missing)} data file(s) in the source package "
        f"are not reachable from the installed package: {shown}"
    ]


def check_metadata(
    distributions: list[Distribution],
    *,
    core: str = "agnara",
) -> list[str]:
    """Versions agree, and every adapter still declares its dependency on core."""
    problems: list[str] = []
    versions: dict[str, str] = {}

    for distribution in distributions:
        try:
            versions[distribution.name] = importlib.metadata.version(distribution.name)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{distribution.name}: no installed distribution metadata")
            continue

        if distribution.name == core:
            continue
        requires = importlib.metadata.requires(distribution.name) or []
        # `Requires-Dist: agnara` and `agnara>=1; extra == "x"` both start with
        # the name, so compare the leading identifier rather than the whole
        # specifier -- this asserts the dependency exists, not its bound.
        declared = {requirement.split(maxsplit=1)[0].split(";")[0] for requirement in requires}
        declared = {
            name.split("[")[0].split("=")[0].split("<")[0].split(">")[0] for name in declared
        }
        if core not in declared:
            problems.append(
                f"{distribution.name}: installed metadata does not declare a "
                f"dependency on {core} (requires: {sorted(declared)})"
            )

    distinct = set(versions.values())
    if len(distinct) > 1:
        # ADR 0021 keeps every pre-one version synchronized.
        detail = ", ".join(f"{name}=={version}" for name, version in sorted(versions.items()))
        problems.append(f"installed versions are not synchronized: {detail}")
    return problems


def run(workspace: Path, *, require_installed: bool) -> tuple[int, list[str]]:
    """Returns an exit code and the lines to report."""
    distributions, problems = discover(workspace)
    for distribution in distributions:
        failures = check_import(
            distribution,
            workspace=workspace,
            require_installed=require_installed,
        )
        problems.extend(failures)
        if not failures:
            # Resolving resources in a package that did not import reports the
            # import failure a second time rather than anything new.
            problems.extend(check_package_data(distribution, workspace=workspace))
    problems.extend(check_metadata(distributions))

    if problems:
        return 1, problems
    names = ", ".join(distribution.name for distribution in distributions)
    return 0, [f"checked {len(distributions)} installed distributions: {names}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="the repository checkout that defines the expected distributions",
    )
    parser.add_argument(
        "--require-installed",
        action="store_true",
        help="also assert nothing resolved from the workspace source tree",
    )
    arguments = parser.parse_args(argv)

    code, lines = run(arguments.workspace, require_installed=arguments.require_installed)
    for line in lines:
        # Say what was inspected on success too. A gate that prints nothing
        # cannot be told apart from one that never ran.
        print(f"::error::{line}" if code else line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
