"""Verify an SBOM actually describes the built candidate.

`generate_sbom.py` produces the document; this reads it back against the
files on disk and the reviewed manifest. Keeping them apart is the point. A
generator that validates its own output only proves it is self-consistent,
which is exactly what a document describing the wrong tree also is.

The failure this guards against is the ordinary one: an SBOM generated from a
development environment, or from a previous build, that looks complete and
describes something nobody published. So the checks are about correspondence
rather than shape:

* every reviewed distribution appears, at the dispatched version;
* every recorded first-party digest matches the bytes in `--dist`;
* the runtime dependency graph is present and the development group is not;
* the document is a CycloneDX document of the expected revision.

Exit status is 0 when the SBOM can be trusted as a description of this
candidate, and 1 with an explanation otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from distributions import load as load_manifest

EXPECTED_FORMAT = "CycloneDX"
EXPECTED_SPEC = "1.6"

#: Names that belong to the development group only. Finding one means the
#: document was produced from an environment rather than from the lockfile's
#: runtime resolution. `pydantic` and `starlette` are deliberately absent from
#: this list: they are development fixtures *and* genuine transitive runtime
#: requirements of the MCP SDK, so their presence is correct.
DEVELOPMENT_ONLY = frozenset(
    {
        "pytest",
        "ruff",
        "ty",
        "hypothesis",
        "playwright",
        "django",
        "litestar",
        "sqlalchemy",
        "msgspec",
        "fastapi",
        "opentelemetry-sdk",
        "pyyaml",
        "sortedcontainers",
    }
)

FIRST_PARTY = {"name": "agnara:role", "value": "first-party"}
RUNTIME_DEPENDENCY = {"name": "agnara:role", "value": "runtime-dependency"}


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _role(component: dict[str, Any], role: dict[str, str]) -> bool:
    return role in component.get("properties", [])


def verify(sbom: Path, workspace: Path, dist: Path, version: str) -> list[str]:
    """Return every reason the SBOM cannot be trusted, or an empty list."""
    problems: list[str] = []

    try:
        document = json.loads(sbom.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"no SBOM at {sbom}"]
    except json.JSONDecodeError as error:
        return [f"{sbom} is not valid JSON: {error}"]

    if document.get("bomFormat") != EXPECTED_FORMAT:
        problems.append(f"bomFormat is {document.get('bomFormat')!r}, expected {EXPECTED_FORMAT!r}")
    if document.get("specVersion") != EXPECTED_SPEC:
        problems.append(
            f"specVersion is {document.get('specVersion')!r}, expected {EXPECTED_SPEC!r}"
        )
    if not str(document.get("serialNumber", "")).startswith("urn:uuid:"):
        problems.append("the document carries no urn:uuid serial number")

    components = document.get("components")
    if not isinstance(components, list) or not components:
        return [*problems, "the document lists no components"]

    described = {
        component.get("name"): component for component in components if isinstance(component, dict)
    }

    # --- the reviewed set, at this version, matching these bytes ---------
    reviewed = load_manifest(workspace).names
    for project in sorted(reviewed):
        component = described.get(_normalize(project))
        if component is None:
            problems.append(f"{project} is in the reviewed set but absent from the SBOM")
            continue
        if not _role(component, FIRST_PARTY):
            problems.append(f"{project} is not marked first-party")
        if component.get("version") != version:
            problems.append(
                f"{project} is described at {component.get('version')!r}, not {version!r}"
            )
            continue

        stem = project.replace("-", "_")
        expected = {
            _digest(path)
            for path in (
                dist / f"{stem}-{version}-py3-none-any.whl",
                dist / f"{stem}-{version}.tar.gz",
            )
            if path.is_file()
        }
        if len(expected) != 2:
            problems.append(f"{project} {version}: both built files are not present in {dist}")
            continue
        recorded = {
            entry.get("content")
            for entry in component.get("hashes", [])
            if entry.get("alg") == "SHA-256"
        }
        if recorded != expected:
            problems.append(
                f"{project}: the SBOM digests do not match the built files. "
                "The document describes a different build."
            )

    # --- the runtime graph, and nothing from the development group -------
    dependencies = [component for component in components if _role(component, RUNTIME_DEPENDENCY)]
    if not dependencies:
        problems.append("the SBOM records no runtime dependencies")

    leaked = sorted(DEVELOPMENT_ONLY & set(described))
    if leaked:
        problems.append(
            "development-only components are present, so the SBOM describes an "
            f"environment rather than the candidate: {', '.join(leaked)}"
        )

    unversioned = sorted(
        str(component.get("name")) for component in components if not component.get("version")
    )
    if unversioned:
        problems.append(f"components without a version: {', '.join(unversioned)}")

    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    arguments = parser.parse_args(argv)

    problems = verify(
        arguments.sbom.resolve(),
        arguments.workspace.resolve(),
        arguments.dist.resolve(),
        arguments.version,
    )
    if problems:
        print(f"error: {arguments.sbom} does not describe this candidate:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"{arguments.sbom} describes the {arguments.version} candidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
