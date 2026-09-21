"""Generate a CycloneDX SBOM for the reviewed distribution candidate.

An SBOM is only useful if it describes the thing that will be published. The
easy mistake -- and the one this script exists to avoid -- is scanning the
development environment and shipping a document that lists `pytest`, `ruff`
and a local interpreter alongside the real runtime graph. What gets published
is seven first-party distributions plus whatever an installer must resolve for
them, so those are the only components here.

Two inputs, both already the repository's source of truth:

* `docs/distributions.json` names the reviewed publication set, and the built
  files in `--dist` supply each one's real SHA-256.
* `uv export --locked --no-dev` supplies the resolved runtime dependency graph
  with the hashes recorded in `uv.lock`.

The document is deterministic. Given the same lockfile and the same built
bytes it is byte-identical, because a reviewer comparing two SBOMs needs the
difference to mean something. That rules out a wall-clock timestamp and a
random serial number: the timestamp comes from `SOURCE_DATE_EPOCH` when set
and is otherwise omitted, and the serial number is a UUID derived from the
document's own content.

This is an inventory, not an attestation. It records what went in; it does not
prove who built it. Provenance and signing for the published files come from
PEP 740 attestations, which `pypa/gh-action-pypi-publish` produces under the
workflow's own OIDC identity -- see `SECURITY.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from distributions import load as load_manifest

#: The CycloneDX specification this document claims. Pinned deliberately: a
#: consumer must not have to guess which revision the fields belong to.
SPEC_VERSION = "1.6"

#: A stable namespace for deriving a content-addressed serial number. Any
#: fixed UUID works; this one is arbitrary and never interpreted.
_SERIAL_NAMESPACE = uuid.UUID("6f1b4d9a-3c2e-4f57-9a0b-2d8e5c71a4f3")

#: `name==version` optionally followed by an environment marker.
_REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)==(?P<version>[^\s;\\]+)(?:\s*;\s*(?P<marker>[^\\]+?))?\s*\\?$"
)
_HASH = re.compile(r"^\s*--hash=(?P<algorithm>[a-z0-9]+):(?P<value>[0-9a-f]+)\s*\\?$")


class SbomError(RuntimeError):
    """The SBOM could not be produced from trustworthy inputs."""


def _normalize(name: str) -> str:
    """PEP 503 normalization, so one project has one spelling."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _purl(name: str, version: str) -> str:
    return f"pkg:pypi/{_normalize(name)}@{version}"


def export_locked_requirements(workspace: Path) -> str:
    """Resolve the runtime graph from the lockfile, never from the environment.

    `--locked` fails rather than re-resolving, so a stale lockfile is an error
    instead of a silently different document. `--no-dev` drops the test and
    tooling group, and `--no-emit-workspace` drops the first-party members,
    which are added separately from the built files themselves.
    """
    command = [
        "uv",
        "export",
        "--locked",
        "--all-packages",
        "--no-dev",
        "--no-emit-workspace",
        "--format",
        "requirements.txt",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:  # pragma: no cover - environment defect
        raise SbomError("uv is not available; cannot resolve the locked graph") from error
    if completed.returncode != 0:
        raise SbomError(
            f"`uv export --locked` failed with exit code {completed.returncode}. "
            "The lockfile is out of date or the workspace does not resolve.\n"
            f"{completed.stderr.strip()}"
        )
    return completed.stdout


def parse_requirements(exported: str) -> list[dict[str, Any]]:
    """Read `name==version` plus recorded hashes out of an export.

    Markers are kept verbatim as a property rather than evaluated: which
    platform a dependency applies to is part of the description, and deciding
    it here would make the document specific to whichever runner produced it.
    """
    components: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in exported.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        hash_match = _HASH.match(line)
        if hash_match is not None:
            if current is None:
                raise SbomError(f"a hash appears before any requirement: {line!r}")
            current["hashes"].append(
                {
                    "alg": hash_match.group("algorithm").upper().replace("SHA", "SHA-"),
                    "content": hash_match.group("value"),
                }
            )
            continue
        requirement = _REQUIREMENT.match(line.strip())
        if requirement is None:
            raise SbomError(f"unrecognized requirement line: {line!r}")
        current = {
            "name": requirement.group("name"),
            "version": requirement.group("version"),
            "marker": (requirement.group("marker") or "").strip(),
            "hashes": [],
        }
        components.append(current)

    if not components:
        raise SbomError("the locked export contained no runtime dependencies")
    return components


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def first_party_components(workspace: Path, dist: Path, version: str) -> list[dict[str, Any]]:
    """Describe the reviewed set from the files that were actually built.

    Every reviewed distribution must be present as both a wheel and an sdist.
    A missing file is an error rather than an omitted component: an SBOM that
    quietly describes six of seven distributions is worse than none, because
    it looks complete.
    """
    reviewed = load_manifest(workspace).names
    components: list[dict[str, Any]] = []

    for project in sorted(reviewed):
        stem = project.replace("-", "_")
        artifacts = {
            "wheel": dist / f"{stem}-{version}-py3-none-any.whl",
            "sdist": dist / f"{stem}-{version}.tar.gz",
        }
        missing = sorted(kind for kind, path in artifacts.items() if not path.is_file())
        if missing:
            raise SbomError(
                f"{project} {version}: no built {', '.join(missing)} in {dist}. "
                "Build the candidate before describing it."
            )
        components.append(
            {
                "type": "library",
                "bom-ref": _purl(project, version),
                "name": _normalize(project),
                "version": version,
                "purl": _purl(project, version),
                "scope": "required",
                "properties": [
                    {"name": "agnara:role", "value": "first-party"},
                ],
                "hashes": [
                    {"alg": "SHA-256", "content": _digest(path)}
                    for _, path in sorted(artifacts.items())
                ],
            }
        )
    return components


def dependency_components(requirements: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for requirement in requirements:
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": _purl(requirement["name"], requirement["version"]),
            "name": _normalize(requirement["name"]),
            "version": requirement["version"],
            "purl": _purl(requirement["name"], requirement["version"]),
            "scope": "required",
            "properties": [{"name": "agnara:role", "value": "runtime-dependency"}],
        }
        if requirement["marker"]:
            component["properties"].append(
                {"name": "agnara:environment-marker", "value": requirement["marker"]}
            )
        if requirement["hashes"]:
            component["hashes"] = sorted(
                requirement["hashes"], key=lambda entry: (entry["alg"], entry["content"])
            )
        components.append(component)
    return components


def _source_date() -> str | None:
    """A reproducible timestamp, or none at all.

    `SOURCE_DATE_EPOCH` is the ecosystem's convention for exactly this: a
    build that wants a timestamp supplies a deterministic one. Reading the
    wall clock instead would make two SBOMs of identical inputs differ.
    """
    import os

    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        return None
    try:
        epoch = int(raw)
    except ValueError as error:
        raise SbomError(f"SOURCE_DATE_EPOCH is not an integer: {raw!r}") from error
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat().replace("+00:00", "Z")


def build_document(workspace: Path, dist: Path, version: str) -> dict[str, Any]:
    requirements = parse_requirements(export_locked_requirements(workspace))
    components = first_party_components(workspace, dist, version) + dependency_components(
        requirements
    )
    components.sort(key=lambda component: (component["name"], component["version"]))

    metadata: dict[str, Any] = {
        "tools": {
            "components": [
                {
                    "type": "application",
                    "name": "agnara-generate-sbom",
                    "version": SPEC_VERSION,
                }
            ]
        },
        "component": {
            "type": "application",
            "bom-ref": f"pkg:generic/agnara@{version}",
            "name": "agnara",
            "version": version,
            "description": "The reviewed Agnara publication set.",
        },
    }
    timestamp = _source_date()
    if timestamp is not None:
        metadata["timestamp"] = timestamp

    document: dict[str, Any] = {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "version": 1,
        "metadata": metadata,
        "components": components,
    }
    # Content-addressed, so re-describing identical inputs yields an identical
    # document rather than a new random identity every run.
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"))
    document["serialNumber"] = f"urn:uuid:{uuid.uuid5(_SERIAL_NAMESPACE, payload)}"
    return document


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the document here instead of standard output.",
    )
    arguments = parser.parse_args(argv)

    try:
        document = build_document(
            arguments.workspace.resolve(), arguments.dist.resolve(), arguments.version
        )
    except SbomError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    rendered = render(document)
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
        first_party = sum(
            1
            for component in document["components"]
            if {"name": "agnara:role", "value": "first-party"} in component.get("properties", [])
        )
        print(
            f"wrote {arguments.output} "
            f"({first_party} first-party, {len(document['components']) - first_party} dependencies)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
