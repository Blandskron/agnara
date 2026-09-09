"""Assert the first-party distributions are built and usable.

The packaging gate used to build seven distributions and install one. Building
a wheel proves it can be produced; it does not prove an installer can resolve
its dependencies, or that the package it contains imports from where it was
installed to. Those are different claims, and only the second is what a user
experiences.

Both are checked here, in two modes, because they share the one thing that
must not be duplicated: what the expected set of distributions *is*. It is
discovered from the workspace layout rather than listed, so adding a
distribution extends these checks instead of escaping them.

Built artifacts, before anything is installed, including their metadata,
archive contents, package data and entry points:

    python scripts/check_distributions.py --workspace <checkout> --dist dist/

Installed distributions, from inside the environment they were installed into:

    python scripts/check_distributions.py --workspace <checkout> \
        --require-installed

The second mode runs in an environment that holds nothing but the built
wheels, so this script imports **only the standard library** -- a third-party
import here would make the gate depend on a package the gate exists to
validate.

``--require-installed`` additionally asserts that nothing resolved from the
workspace source tree. It is off by default because the development
environment installs the workspace packages from ``packages/*/src``, where
importing from the source tree is correct rather than a defect.
"""

from __future__ import annotations

import argparse
import configparser
import email.parser
import importlib
import importlib.metadata
import importlib.resources
import json
import os
import re
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: `packages/<distribution>/src/<import name>/__init__.py`, the layout
#: `tests/architecture/test_workspace_layout.py` enforces and ADR 0017 fixes.
SRC_LAYOUT = "src"

#: Where the reviewed publication set is declared, relative to the workspace.
#:
#: The release contract is deliberately explicit. Workspace discovery still
#: detects additions, while this allowlist prevents a newly added package from
#: being uploaded merely because ``uv build --all-packages`` found it. The
#: allowlist is read from ``docs/distributions.json`` rather than retyped here,
#: because the same seven names were previously spelled out in five places and
#: nothing compared them.
#:
#: ``scripts/distributions.py`` owns that file and parses it for every other
#: tool. This module deliberately does not import it: the installed-artifact
#: mode runs as ``python -I .../scripts/check_distributions.py``, and ``-I``
#: implies ``-P``, so the script's own directory is not on ``sys.path`` and a
#: sibling import would fail exactly where the gate matters most.
#: ``tests/release/test_publication_set.py`` asserts the two readers agree.
MANIFEST_RELATIVE = Path("docs") / "distributions.json"


def shipped_distributions(workspace: Path) -> dict[str, str]:
    """The reviewed publication set: distribution name -> import package."""
    path = workspace / MANIFEST_RELATIVE
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise ValueError(f"{path}: unsupported schema_version")
    entries = document["distributions"]
    shipped = {entry["name"]: entry["import_name"] for entry in entries}
    if len(shipped) != len(entries):
        raise ValueError(f"{path}: distribution names must be unique")
    return shipped


FORBIDDEN_ARCHIVE_PARTS = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "experiments", "tests"}
)
SENSITIVE_FILENAMES = frozenset({".env", ".pypirc", "id_rsa", "id_ed25519"})
SECRET_SIGNATURES = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?<![A-Za-z0-9_-])pypi-[A-Za-z0-9_-]{50,255}(?![A-Za-z0-9_-])"),
    re.compile(rb"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{36,255}(?![A-Za-z0-9])"),
    re.compile(rb"(?<![0-9A-Z])AKIA[0-9A-Z]{16}(?![0-9A-Z])"),
)


@dataclass(frozen=True, slots=True)
class Distribution:
    """One first-party distribution and the package it installs."""

    name: str
    import_name: str


def check_release_set(distributions: list[Distribution], shipped: dict[str, str]) -> list[str]:
    """The discovered workspace must equal the reviewed publication set."""
    actual = {distribution.name: distribution.import_name for distribution in distributions}
    if actual == shipped:
        return []
    missing = sorted(set(shipped) - set(actual))
    unexpected = sorted(set(actual) - set(shipped))
    mismatched = sorted(
        name for name in set(actual) & set(shipped) if actual[name] != shipped[name]
    )
    return [
        "workspace distribution set differs from the reviewed release set: "
        f"missing={missing}, unexpected={unexpected}, import-name mismatches={mismatched}"
    ]


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


#: What `uv build` emits per distribution, and the only files that count as
#: artifacts. `uv build` also writes its own `.gitignore` into the output
#: directory; that is its bookkeeping, not something being shipped.
ARTIFACT_SUFFIXES = (".whl", ".tar.gz")


def check_built_artifacts(
    distributions: list[Distribution],
    dist_dir: Path,
) -> list[str]:
    """Exactly one wheel and one sdist per distribution, and nothing else."""
    if not dist_dir.is_dir():
        return [f"no build output directory at {dist_dir}"]

    artifacts = sorted(
        path
        for path in dist_dir.iterdir()
        if path.is_file() and path.name.endswith(ARTIFACT_SUFFIXES)
    )

    problems: list[str] = []
    for distribution in distributions:
        # PEP 427/625 normalize the hyphen in a distribution name to an
        # underscore in the artifact filename.
        stem = distribution.name.replace("-", "_") + "-"
        wheels = [path.name for path in artifacts if path.name.startswith(stem)]
        sdists = [name for name in wheels if name.endswith(".tar.gz")]
        wheels = [name for name in wheels if name.endswith(".whl")]
        if len(wheels) != 1:
            problems.append(f"{distribution.name}: expected 1 wheel, found {wheels}")
        if len(sdists) != 1:
            problems.append(f"{distribution.name}: expected 1 sdist, found {sdists}")

    known = tuple(d.name.replace("-", "_") + "-" for d in distributions)
    surplus = sorted(path.name for path in artifacts if not path.name.startswith(known))
    if surplus:
        # A stale artifact would let a later glob validate, or publish,
        # something this build did not produce.
        problems.append(f"unexpected artifacts in {dist_dir}: {surplus}")
    return problems


def _project(workspace: Path, distribution: Distribution) -> dict[str, Any]:
    path = workspace / "packages" / distribution.name / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]


def _normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _canonical_requirement(requirement: str) -> tuple[str, str, tuple[str, ...], str]:
    """Enough PEP 508 normalization for repository-owned dependency metadata."""
    match = re.fullmatch(
        r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]+\])?\s*([^;@]*?)\s*(?:;\s*(.*))?",
        requirement,
    )
    if match is None or "@" in requirement:
        raise ValueError(f"unsupported direct/editable dependency: {requirement!r}")
    extras = ""
    if match[2]:
        extras = ",".join(sorted(part.strip().lower() for part in match[2][1:-1].split(",")))
    clauses = tuple(sorted(part.strip() for part in match[3].split(",") if part.strip()))
    marker = re.sub(r"\s+", " ", match[4] or "").strip()
    return _normalized_name(match[1]), extras, clauses, marker


def _safe_archive_names(names: list[str], distribution: str) -> list[str]:
    problems: list[str] = []
    for name in names:
        normalized = name.replace("\\", "/")
        parts = tuple(part for part in normalized.split("/") if part)
        if name.startswith(("/", "\\")) or "\\" in name or ".." in parts:
            problems.append(f"{distribution}: unsafe archive member {name!r}")
        lowered = {part.lower() for part in parts}
        if lowered & FORBIDDEN_ARCHIVE_PARTS or any(
            part.endswith((".pyc", ".pyo")) for part in lowered
        ):
            problems.append(f"{distribution}: development/cache file shipped: {name}")
        if lowered & SENSITIVE_FILENAMES:
            problems.append(f"{distribution}: sensitive filename shipped: {name}")
    return problems


def _contains_workspace_path(payload: bytes, workspace: Path) -> bool:
    """Whether artifact bytes retain either native or URI build-host provenance."""
    normalized = str(workspace.resolve()).replace("\\", "/").encode().lower()
    uri = workspace.resolve().as_uri().encode().lower()
    candidate = payload.replace(b"\\", b"/").lower()
    return normalized in candidate or uri in candidate


def _contains_secret_signature(payload: bytes) -> bool:
    """Detect credential formats that must never occur in a distribution."""
    return any(pattern.search(payload) is not None for pattern in SECRET_SIGNATURES)


def _check_wheel(
    distribution: Distribution,
    *,
    workspace: Path,
    wheel: Path,
) -> list[str]:
    project = _project(workspace, distribution)
    problems: list[str] = []
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        problems.extend(_safe_archive_names(names, distribution.name))
        payloads = {name: archive.read(name) for name in names if not name.endswith("/")}
        leaking = [
            name
            for name, payload in payloads.items()
            if _contains_workspace_path(payload, workspace)
        ]
        if leaking:
            problems.append(f"{distribution.name}: wheel retains the local build path in {leaking}")
        secrets = [
            name
            for name, payload in payloads.items()
            if "/_vendor/" not in f"/{name}" and _contains_secret_signature(payload)
        ]
        if secrets:
            problems.append(
                f"{distribution.name}: wheel contains a recognized credential "
                f"signature in {secrets}"
            )
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            return [*problems, f"{distribution.name}: wheel must contain exactly one METADATA"]
        raw_metadata = archive.read(metadata_names[0]).replace(b"\r\n", b"\n")
        metadata = email.parser.BytesParser().parsebytes(raw_metadata)

        expected_headers = {
            "Name": distribution.name,
            "Version": project["version"],
            "Requires-Python": ">=3.14",
            "License": "Apache-2.0",
            "Description-Content-Type": "text/markdown",
            "Author-email": "Agnara Maintainers <maintainers@agnara.dev>",
        }
        for header, expected in expected_headers.items():
            actual = metadata.get(header)
            if header == "Name" and actual is not None:
                matches = _normalized_name(actual) == _normalized_name(expected)
            else:
                matches = actual == expected
            if not matches:
                problems.append(
                    f"{distribution.name}: wheel {header} is {actual!r}, expected {expected!r}"
                )
        readme = project.get("readme")
        expected_readme = (
            (workspace / "packages" / distribution.name / readme).read_text(encoding="utf-8")
            if isinstance(readme, str)
            else ""
        )
        _, separator, raw_description = raw_metadata.partition(b"\n\n")
        description = raw_description.decode("utf-8") if separator else ""
        if not description.strip():
            problems.append(f"{distribution.name}: wheel contains no README description")
        elif description.strip() != expected_readme.strip():
            problems.append(
                f"{distribution.name}: wheel description differs from the source README"
            )
        if "LICENSE" not in (metadata.get_all("License-File") or []):
            problems.append(f"{distribution.name}: wheel metadata does not declare LICENSE")
        expected_urls = {f"{label}, {url}" for label, url in project.get("urls", {}).items()}
        actual_urls = set(metadata.get_all("Project-URL") or [])
        if actual_urls != expected_urls:
            problems.append(
                f"{distribution.name}: project URLs differ from pyproject.toml: "
                f"expected={sorted(expected_urls)}, actual={sorted(actual_urls)}"
            )
        expected_classifiers = set(project.get("classifiers", []))
        actual_classifiers = set(metadata.get_all("Classifier") or [])
        if actual_classifiers != expected_classifiers:
            problems.append(
                f"{distribution.name}: classifiers differ from pyproject.toml: "
                f"expected={sorted(expected_classifiers)}, actual={sorted(actual_classifiers)}"
            )

        try:
            expected_requirements = {
                _canonical_requirement(requirement)
                for requirement in project.get("dependencies", [])
            }
            actual_requirements = {
                _canonical_requirement(requirement)
                for requirement in (metadata.get_all("Requires-Dist") or [])
            }
        except ValueError as exc:
            problems.append(f"{distribution.name}: {exc}")
        else:
            if actual_requirements != expected_requirements:
                problems.append(
                    f"{distribution.name}: wheel dependencies differ from pyproject.toml: "
                    f"expected={sorted(expected_requirements)}, "
                    f"actual={sorted(actual_requirements)}"
                )

        expected_scripts = project.get("scripts", {})
        entry_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        actual_scripts: dict[str, str] = {}
        if entry_names:
            if len(entry_names) != 1:
                problems.append(
                    f"{distribution.name}: wheel contains multiple entry_points.txt files"
                )
            else:
                parser = configparser.ConfigParser()
                parser.optionxform = str
                parser.read_string(archive.read(entry_names[0]).decode("utf-8"))
                if parser.has_section("console_scripts"):
                    actual_scripts = dict(parser["console_scripts"])
        if actual_scripts != expected_scripts:
            problems.append(
                f"{distribution.name}: console scripts differ from pyproject.toml: "
                f"expected={expected_scripts}, actual={actual_scripts}"
            )

        data = data_files(workspace, distribution)
        required = [f"{distribution.import_name}/__init__.py"]
        required.extend(f"{distribution.import_name}/{relative}" for relative in data)
        missing = [name for name in required if name not in names]
        if missing:
            problems.append(f"{distribution.name}: wheel is missing package files: {missing}")
        mismatched_data = [
            relative
            for relative in data
            if f"{distribution.import_name}/{relative}" in names
            and archive.read(f"{distribution.import_name}/{relative}")
            != (
                workspace
                / "packages"
                / distribution.name
                / SRC_LAYOUT
                / distribution.import_name
                / relative
            ).read_bytes()
        ]
        if mismatched_data:
            problems.append(
                f"{distribution.name}: wheel package data differs from source: {mismatched_data}"
            )
        license_names = [name for name in names if name.endswith(".dist-info/licenses/LICENSE")]
        if len(license_names) != 1:
            problems.append(f"{distribution.name}: wheel does not contain LICENSE")
        elif archive.read(license_names[0]) != (workspace / "LICENSE").read_bytes():
            problems.append(f"{distribution.name}: wheel LICENSE differs from repository LICENSE")
    return problems


def _check_sdist(
    distribution: Distribution,
    *,
    workspace: Path,
    sdist: Path,
) -> list[str]:
    project = _project(workspace, distribution)
    root = f"{distribution.name.replace('-', '_')}-{project['version']}"
    problems: list[str] = []
    with tarfile.open(sdist, mode="r:gz") as archive:
        names = archive.getnames()
        problems.extend(_safe_archive_names(names, distribution.name))
        leaking: list[str] = []
        secrets: list[str] = []
        for member in archive.getmembers():
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            if stream is not None:
                payload = stream.read()
                if _contains_workspace_path(payload, workspace):
                    leaking.append(member.name)
                if "/_vendor/" not in f"/{member.name}" and _contains_secret_signature(payload):
                    secrets.append(member.name)
        if leaking:
            problems.append(f"{distribution.name}: sdist retains the local build path in {leaking}")
        if secrets:
            problems.append(
                f"{distribution.name}: sdist contains a recognized credential "
                f"signature in {secrets}"
            )
        required = {
            f"{root}/LICENSE",
            f"{root}/README.md",
            f"{root}/pyproject.toml",
            f"{root}/src/{distribution.import_name}/__init__.py",
        }
        missing = sorted(required - set(names))
        if missing:
            problems.append(f"{distribution.name}: sdist is missing required files: {missing}")
        source_files = {
            "LICENSE": workspace / "LICENSE",
            "README.md": workspace / "packages" / distribution.name / "README.md",
            "pyproject.toml": workspace / "packages" / distribution.name / "pyproject.toml",
        }
        mismatched: list[str] = []
        for relative, source in source_files.items():
            member_name = f"{root}/{relative}"
            try:
                member = archive.getmember(member_name)
            except KeyError:
                continue
            stream = archive.extractfile(member)
            if stream is None or stream.read() != source.read_bytes():
                mismatched.append(relative)
        if mismatched:
            problems.append(f"{distribution.name}: sdist files differ from source: {mismatched}")
        roots = {name.split("/", 1)[0] for name in names}
        if roots != {root}:
            problems.append(
                f"{distribution.name}: sdist has unexpected archive roots: {sorted(roots)}"
            )
    return problems


def check_artifact_contents(
    distributions: list[Distribution],
    *,
    workspace: Path,
    dist_dir: Path,
) -> list[str]:
    """Inspect wheel/sdist contents and metadata before either can be published."""
    problems: list[str] = []
    for distribution in distributions:
        project = _project(workspace, distribution)
        stem = distribution.name.replace("-", "_")
        wheel = dist_dir / f"{stem}-{project['version']}-py3-none-any.whl"
        sdist = dist_dir / f"{stem}-{project['version']}.tar.gz"
        if wheel.is_file():
            try:
                problems.extend(_check_wheel(distribution, workspace=workspace, wheel=wheel))
            except zipfile.BadZipFile as exc:
                problems.append(f"{distribution.name}: invalid wheel archive: {exc}")
        if sdist.is_file():
            try:
                problems.extend(_check_sdist(distribution, workspace=workspace, sdist=sdist))
            except tarfile.TarError as exc:
                problems.append(f"{distribution.name}: invalid sdist archive: {exc}")
    return problems


def check_metadata(
    distributions: list[Distribution],
    *,
    core: str = "agnara",
    expected_version: str | None = None,
) -> list[str]:
    """Versions agree, and every adapter pins that exact core version."""
    problems: list[str] = []
    versions: dict[str, str] = {}
    requirements: dict[str, list[str]] = {}

    for distribution in distributions:
        try:
            versions[distribution.name] = importlib.metadata.version(distribution.name)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{distribution.name}: no installed distribution metadata")
            continue

        if distribution.name == core:
            continue
        requirements[distribution.name] = importlib.metadata.requires(distribution.name) or []

    distinct = set(versions.values())
    if len(distinct) > 1:
        # ADR 0021 keeps every pre-one version synchronized.
        detail = ", ".join(f"{name}=={version}" for name, version in sorted(versions.items()))
        problems.append(f"installed versions are not synchronized: {detail}")
    if expected_version is not None:
        wrong = {name: version for name, version in versions.items() if version != expected_version}
        if wrong:
            problems.append(f"installed versions do not match expected {expected_version}: {wrong}")

    normalized_core = core.lower().replace("_", "-")
    for adapter, declared in sorted(requirements.items()):
        core_requirements: list[tuple[str | None, str]] = []
        for requirement in declared:
            match = re.match(
                r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]+\])?\s*(.*)$",
                requirement,
            )
            if match and match[1].lower().replace("_", "-") == normalized_core:
                core_requirements.append((match[2], re.sub(r"\s+", "", match[3])))
        if not core_requirements:
            problems.append(
                f"{adapter}: installed metadata does not declare a dependency on {core}"
            )
            continue
        expected = f"=={versions[adapter]}"
        if core_requirements != [(None, expected)]:
            rendered = [
                f"{core}{extra or ''}{constraint}" for extra, constraint in core_requirements
            ]
            problems.append(
                f"{adapter}: installed metadata must require {core}{expected} exactly "
                f"(found: {rendered})"
            )
    return problems


def run(
    workspace: Path,
    *,
    require_installed: bool = False,
    dist_dir: Path | None = None,
    expected_version: str | None = None,
) -> tuple[int, list[str]]:
    """Returns an exit code and the lines to report."""
    distributions, problems = discover(workspace)
    try:
        shipped = shipped_distributions(workspace)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        # Without the manifest there is no reviewed set to compare against, so
        # the comparison is reported as missing rather than skipped. Whatever
        # discovery already found is still reported alongside it: an unreadable
        # manifest and an empty workspace are different failures.
        problems.append(f"cannot read the reviewed publication set: {exc}")
    else:
        problems.extend(check_release_set(distributions, shipped))
    if expected_version is not None:
        wrong = {
            distribution.name: _project(workspace, distribution)["version"]
            for distribution in distributions
            if _project(workspace, distribution)["version"] != expected_version
        }
        if wrong:
            problems.append(f"workspace versions do not match expected {expected_version}: {wrong}")

    if dist_dir is not None:
        # Artifacts are checked before anything is installed, so importing
        # here would report failures that say nothing about the build.
        problems.extend(check_built_artifacts(distributions, dist_dir))
        if not problems:
            problems.extend(
                check_artifact_contents(distributions, workspace=workspace, dist_dir=dist_dir)
            )
        if problems:
            return 1, problems
        names = ", ".join(distribution.name for distribution in distributions)
        return 0, [f"built {len(distributions)} distributions: {names}"]

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
    problems.extend(check_metadata(distributions, expected_version=expected_version))

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
        "--dist",
        type=Path,
        default=None,
        help="check the built artifacts in this directory instead of the installation",
    )
    parser.add_argument(
        "--require-installed",
        action="store_true",
        help="also assert nothing resolved from the workspace source tree",
    )
    parser.add_argument(
        "--expected-version",
        default=None,
        help="require every source and installed distribution to match this version",
    )
    arguments = parser.parse_args(argv)

    code, lines = run(
        arguments.workspace,
        require_installed=arguments.require_installed,
        dist_dir=arguments.dist,
        expected_version=arguments.expected_version,
    )
    if code:
        # Diagnostics may contain metadata or paths controlled by the artifact
        # under inspection. Keep them available to programmatic callers of
        # ``run`` without copying potentially sensitive values into CI logs.
        print(f"::error::distribution validation failed with {len(lines)} problem(s)")
    else:
        # Successful summaries contain only names from the reviewed manifest.
        for line in lines:
            print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
