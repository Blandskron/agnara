"""Decide whether the *publication* of a release may proceed.

`scripts/check_release_readiness.py` answers a different question: is the code
mature enough to close this release. `0.1.0a4` proved that a green answer to
that question is not an answer to this one. Every quality gate passed, the
artifacts were built and validated, the tag was correct -- and the upload still
half-failed, because six of the seven PyPI projects did not exist and nothing
in the repository was responsible for knowing that.

So the two claims are now separate and separately checked:

* **CODE READY** -- `check_release_readiness.py`. The implementation, its
  evidence and the maintainer judgments.
* **PUBLISH READY** -- this script. Everything between a correct commit and
  seven complete distributions on an index: the reviewed set, synchronized
  versions, exact first-party pins, the artifact set, the release notes, the
  tag, and the external registry configuration the repository cannot create
  but must refuse to assume.

The registry part is the one that matters most and is the easiest to fake, so
it is not prose. `docs/releases/publication.json` records the expected Trusted
Publisher configuration -- the common owner/repository/workflow and, per project,
the bootstrap environment, exact PyPI name and pending/active kind -- and who read
each of them back from PyPI, and when. An unconfirmed record is a hard failure;
so is a readback older than the last recorded registry failure, a publisher
kind that disagrees with whether the project exists on the index, a tuple that
is not the identity `release.yml` presents, or a confirmation signed by an
automation identity. That file is a reviewed diff, which is what a paragraph
in a release note was not.

What this file deliberately no longer holds is the per-release human
authorization. `0.1.0a7` was tagged while the record said `UNVERIFIED`, which
burned the version without publishing anything: a JSON field cannot stop a
tag that already exists. The authorization is now the approval of the
protected `pypi` GitHub environment inside the release run, and the tag is
created only after it (ADR 0082). This script keeps the registry facts honest;
`scripts/check_release_preconditions.py` keeps the approval real.

Modes, which compose::

    # offline: the repository's own publish-readiness
    python scripts/check_publication_readiness.py --version 0.1.0a8

    # plus the built artifact set
    python scripts/check_publication_readiness.py --version 0.1.0a8 --dist dist/

    # plus the registry, before publishing: nothing of this version exists yet
    python scripts/check_publication_readiness.py --version 0.1.0a8 --online

    # inside GitHub Actions: the recorded tuple is this run's OIDC identity
    python scripts/check_publication_readiness.py --version 0.1.0a8 --oidc-identity

    # after publishing: all seven are complete, wheel and sdist
    python scripts/check_publication_readiness.py --version 0.1.0a8 \\
        --online --require-published

    # one bootstrap phase at a time (PyPI allows three pending publishers):
    # readbacks are required only for the phase's projects, earlier phases
    # must already be complete on the index, later ones untouched
    python scripts/check_publication_readiness.py --version 0.1.0a8 \\
        --phase bootstrap-1 --online
    python scripts/check_publication_readiness.py --version 0.1.0a8 \\
        --phase bootstrap-1 --online --require-published

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import distributions

ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_RELATIVE = Path("docs") / "releases" / "publication.json"
RELEASE_NOTES_DIR = Path("docs") / "releases"
CHANGELOG_RELATIVE = Path("CHANGELOG.md")
WORKFLOWS_RELATIVE = Path(".github") / "workflows"

SCHEMA_VERSION = 3
VERIFIED = "VERIFIED"

#: How a release is authorized by a human: by approving the protected GitHub
#: approval environment, separate from the bootstrap upload environments.
AUTHORIZATION_MECHANISM = "github-environment"

#: A project that does not exist yet is created by a *pending* publisher; one
#: that exists carries an *active* publisher in its own settings. The two are
#: configured in different places on PyPI, so the record says which it read.
PUBLISHER_KINDS = {"pending": "absent", "active": "existing"}

#: Identities that cannot confirm anything. A confirmation is a human act; a
#: workflow, a bot or an agent writing its own name here would make the record
#: certify itself.
AUTOMATION_IDENTITY = re.compile(
    r"(?i)(\[bot\]|github-actions|dependabot|copilot|codex|claude|chatgpt|openai|anthropic|"
    r"\bbot\b|\bagent\b|automation|workflow|pipeline)"
)

#: The common Trusted Publisher fields every Agnara project must carry. A publisher
#: that differs in any field is a different identity to PyPI, and the upload
#: fails the way `0.1.0a4` failed.
REQUIRED_PUBLISHER = {
    "provider": "github",
    "owner": "Blandskron",
    "repository": "agnara",
    "workflow": "release.yml",
}

AUTHORIZATION_ENVIRONMENT = "pypi"
# Bootstrap only. Pending publishers cannot share an external identity (ADR 0083).
BOOTSTRAP_ENVIRONMENTS = {
    "agnara": "pypi-core",
    "agnara-a2a": "pypi-a2a",
    "agnara-cli": "pypi-cli",
    "agnara-events": "pypi-events",
    "agnara-http": "pypi-http",
    "agnara-mcp": "pypi-mcp",
    "agnara-telemetry": "pypi-telemetry",
}

#: PyPI allows at most three Pending Trusted Publishers at a time per account,
#: so the six new projects cannot all be pending at once. A8 is therefore
#: published in phases: each phase uploads only its projects, verifies what
#: exists so far, and only the last one -- the kernel -- earns the tag. The
#: order is the publication order of ADR 0079: siblings first, `agnara` last.
PHASES: dict[str, tuple[str, ...]] = {
    "bootstrap-1": ("agnara-a2a", "agnara-cli", "agnara-events"),
    "bootstrap-2": ("agnara-http", "agnara-mcp", "agnara-telemetry"),
    "final": ("agnara",),
}
PHASE_ORDER: tuple[str, ...] = tuple(PHASES)
FINAL_PHASE = "final"

DEFAULT_INDEX = "https://pypi.org"
NETWORK_TIMEOUT = 30


def phase_projects(phase: str) -> tuple[str, ...]:
    """The projects a phase uploads."""
    if phase not in PHASES:
        raise Refusal(f"unknown release phase {phase!r}; expected one of {list(PHASES)}")
    return PHASES[phase]


def projects_published_before(phase: str) -> tuple[str, ...]:
    """Everything an earlier phase must already have put on the index."""
    phase_projects(phase)
    before: list[str] = []
    for earlier in PHASE_ORDER:
        if earlier == phase:
            break
        before.extend(PHASES[earlier])
    return tuple(before)


def projects_published_through(phase: str) -> tuple[str, ...]:
    """Everything that must be complete on the index once a phase has run."""
    return (*projects_published_before(phase), *phase_projects(phase))


#: PEP 440 public release versions. Development and local versions are excluded.
VERSION_PATTERN = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:(?:a|b|rc)\d+)?$")

URL_PATTERN = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s<>\"']+")
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(password|passwd|pwd|token|api[-_ ]?key|secret|authorization|credential|"
    r"access[-_ ]?key)(\s*[:=]\s*)([^\s,;]+)"
)
SECRET_TOKEN_PATTERN = re.compile(
    r"(?i)\b(?:bearer\s+)[a-z0-9._~+/=-]+|"
    r"\b(?:gh[pousr]_[a-z0-9_]+|github_pat_[a-z0-9_]+|pypi-[a-z0-9_-]+)\b"
)


class Refusal(Exception):
    """Publication readiness could not even be evaluated."""


def _safe_url_for_log(value: str) -> str:
    """Keep only a URL's non-secret origin for diagnostics."""
    try:
        parsed = urllib.parse.urlsplit(value)
        host = parsed.hostname
        if not parsed.scheme or host is None:
            return "<redacted-url>"
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError:
        return "<redacted-url>"
    return f"{parsed.scheme}://{host}{port}"


def sanitize_for_log(value: object) -> str:
    """Return one log-safe line without URLs or recognizable credentials."""
    message = URL_PATTERN.sub(lambda match: _safe_url_for_log(match.group()), str(value))
    message = SECRET_TOKEN_PATTERN.sub("<redacted>", message)
    message = SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>", message
    )
    return "".join(
        character if not unicodedata.category(character).startswith("C") else " "
        for character in message
    )


def _emit(message: object) -> None:
    safe = sanitize_for_log(message)
    # A plain diagnostic must never become an unintended workflow command.
    print(f" {safe}" if safe.startswith("::") else safe)


def _emit_error(message: object) -> None:
    # GitHub workflow command data requires percent escaping. Newlines and all
    # other control characters have already been collapsed by sanitize_for_log.
    safe = sanitize_for_log(message).replace("%", "%25")
    print(f"::error::{safe}")


# ---------------------------------------------------------------------------
# Repository facts
# ---------------------------------------------------------------------------


def _project(workspace: Path, name: str) -> dict[str, Any]:
    path = workspace / "packages" / name / "pyproject.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError) as exc:
        raise Refusal(f"cannot read project metadata from {path}: {exc}") from exc


def check_workspace(workspace: Path, manifest: distributions.Manifest, version: str) -> list[str]:
    """The seven declared distributions exist, at one version, pinned exactly."""
    problems: list[str] = []

    packages_dir = workspace / "packages"
    on_disk = sorted(child.name for child in packages_dir.iterdir() if child.is_dir())
    if on_disk != sorted(manifest.names):
        problems.append(
            f"packages/ holds {on_disk}, the reviewed publication set is {sorted(manifest.names)}"
        )
        return problems

    for distribution in manifest.distributions:
        project = _project(workspace, distribution.name)
        if project["name"] != distribution.name:
            problems.append(
                f"{distribution.name}: declares the project name {project['name']!r}; "
                "the canonical name is what PyPI matches a Trusted Publisher against"
            )
        if project["version"] != version:
            problems.append(
                f"{distribution.name}: declares {project['version']}, expected {version}"
            )
        requirements = [
            requirement
            for requirement in project.get("dependencies", [])
            if requirement.split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip()
            == manifest.core
        ]
        if distribution.name == manifest.core:
            if requirements:
                problems.append(f"{manifest.core} must not depend on itself")
            continue
        if requirements != [f"{manifest.core}=={version}"]:
            problems.append(
                f"{distribution.name}: must pin {manifest.core}=={version} exactly, "
                f"found {requirements}"
            )
        scripts = sorted(project.get("scripts", {}))
        if scripts != sorted(distribution.console_scripts):
            problems.append(
                f"{distribution.name}: declares console scripts {scripts}, "
                f"the manifest declares {sorted(distribution.console_scripts)}"
            )
    return problems


def check_release_notes(workspace: Path, version: str) -> list[str]:
    """A tagged release publishes these notes; a missing file degrades silently."""
    path = workspace / RELEASE_NOTES_DIR / f"v{version}.md"
    if not path.is_file():
        return [
            f"{path.relative_to(workspace).as_posix()} is missing; release.yml uses it as the "
            "GitHub Release body and falls back to the generated PR list without saying so"
        ]
    text = path.read_text(encoding="utf-8")
    if version not in text:
        return [f"{path.name} never names {version}"]
    return []


def check_changelog(workspace: Path, version: str) -> list[str]:
    """The dated section and the comparison links must name this exact version."""
    path = workspace / CHANGELOG_RELATIVE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refusal(f"cannot read {path}: {exc}") from exc
    problems: list[str] = []
    if not re.search(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", text, re.M):
        problems.append(f"CHANGELOG.md has no dated [{version}] section")
    if f"[{version}]: https://github.com/Blandskron/agnara/compare/" not in text:
        problems.append(f"CHANGELOG.md has no comparison link for [{version}]")
    return problems


def check_no_stale_versions(
    workspace: Path, manifest: distributions.Manifest, version: str
) -> list[str]:
    """No first-party distribution may be left behind at another version.

    `uv.lock` pins every workspace member, so a package whose version was not
    moved shows up here as well as in the metadata check.
    """
    problems: list[str] = []
    lock = workspace / "uv.lock"
    try:
        document = tomllib.loads(lock.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise Refusal(f"cannot read {lock}: {exc}") from exc
    locked = {
        package["name"]: package.get("version")
        for package in document.get("package", [])
        if package.get("name") in set(manifest.names)
    }
    missing = sorted(set(manifest.names) - set(locked))
    if missing:
        problems.append(f"uv.lock does not lock {missing}")
    wrong = {name: found for name, found in sorted(locked.items()) if found != version}
    if wrong:
        problems.append(f"uv.lock records versions other than {version}: {wrong}")
    return problems


def check_tag(workspace: Path, version: str, tag: str | None) -> list[str]:
    """The tag must be annotated, name this checkout, this version, and main."""
    if tag is None:
        return []
    if tag != f"v{version}":
        return [f"tag {tag} does not correspond to version {version}"]
    script = workspace / "scripts" / "check_release_tag.py"
    completed = subprocess.run(
        [sys.executable, str(script), tag],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        return [(completed.stdout + completed.stderr).strip() or f"{tag} was refused"]
    return []


# ---------------------------------------------------------------------------
# Built artifacts
# ---------------------------------------------------------------------------


def check_artifact_set(manifest: distributions.Manifest, dist_dir: Path, version: str) -> list[str]:
    """Exactly one wheel and one sdist per distribution, and nothing else."""
    problems: list[str] = []
    expected: set[str] = set()
    for distribution in manifest.distributions:
        stem = distribution.artifact_stem
        expected.add(f"{stem}-{version}-py3-none-any.whl")
        expected.add(f"{stem}-{version}.tar.gz")

    present = {
        path.name
        for path in dist_dir.iterdir()
        if path.is_file() and (path.name.endswith(".whl") or path.name.endswith(".tar.gz"))
    }
    missing = sorted(expected - present)
    unexpected = sorted(present - expected)
    if missing:
        problems.append(f"missing built artifacts: {missing}")
    if unexpected:
        problems.append(f"unreviewed files in {dist_dir}: {unexpected}")

    wheels = sum(1 for name in present if name.endswith(".whl"))
    sdists = sum(1 for name in present if name.endswith(".tar.gz"))
    count = len(manifest.distributions)
    if wheels != count or sdists != count:
        problems.append(f"expected {count} wheels and {count} sdists, found {wheels} and {sdists}")
    return problems


# ---------------------------------------------------------------------------
# The external registry contract
# ---------------------------------------------------------------------------


def load_publication_record(workspace: Path) -> dict[str, Any]:
    path = workspace / PUBLICATION_RELATIVE
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Refusal(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise Refusal(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise Refusal(f"{path}: unsupported or missing schema_version")
    return document


def _iso_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _confirmation_problems(who: object, when: object, *, subject: str) -> list[str]:
    """A confirmation is a dated human act, or it is nothing."""
    if not who or not when:
        return [f"{subject}: a confirmation must name who verified it and when"]
    problems: list[str] = []
    if not isinstance(who, str) or AUTOMATION_IDENTITY.search(who):
        problems.append(
            f"{subject}: verified_by names an automation identity; only a human readback "
            "of PyPI can confirm a Trusted Publisher"
        )
    if _iso_date(when) is None:
        problems.append(f"{subject}: the confirmation date must be an ISO date (YYYY-MM-DD)")
    return problems


def check_publisher_record(
    workspace: Path, manifest: distributions.Manifest, *, phase: str | None = None
) -> list[str]:
    """A human must have read each Trusted Publisher back from PyPI, recently.

    This is the gate `0.1.0a4` did not have. The information is external to
    the repository and cannot be derived from it, so the repository's job is
    not to guess it but to refuse to proceed without a recorded, reviewed,
    dated readback -- one made after the last time PyPI proved a readback
    wrong, by a person rather than by the pipeline, and consistent with what
    the record itself says about each project.

    With a ``phase``, the readback is required only for the projects that
    phase uploads. PyPI caps pending publishers at three, so the publishers of
    a later phase cannot exist yet and are not demanded; the publishers of an
    earlier phase have already been consumed by a publication the index is
    asked to prove instead. Every project is still held to its canonical name
    and bootstrap environment, and the record as a whole is required to be
    ``VERIFIED`` only when no phase is given.
    """
    document = load_publication_record(workspace)
    where = PUBLICATION_RELATIVE.as_posix()
    problems: list[str] = []
    required = set(manifest.names) if phase is None else set(phase_projects(phase))

    if document.get("status") != VERIFIED:
        if phase is None:
            problems.append(f"{where}: top-level status is not {VERIFIED}")
    else:
        problems.extend(
            _confirmation_problems(
                document.get("confirmed_by"), document.get("confirmed_on"), subject=where
            )
        )
    publisher = document.get("publisher")
    if publisher != REQUIRED_PUBLISHER:
        problems.append(
            f"{where}: publisher tuple does not match the required GitHub Trusted Publisher "
            "identity"
        )

    authorization = document.get("release_authorization")
    if not isinstance(authorization, dict) or (
        authorization.get("mechanism") != AUTHORIZATION_MECHANISM
        or authorization.get("environment") != AUTHORIZATION_ENVIRONMENT
    ):
        problems.append(
            f"{where}: release_authorization must be the {AUTHORIZATION_MECHANISM} "
            f"{AUTHORIZATION_ENVIRONMENT!r}; a release is authorized by approving that "
            "environment, not by editing this file"
        )

    failure = document.get("last_registry_failure")
    failed_on: date | None = None
    if failure is not None:
        failed_on = _iso_date(failure.get("on")) if isinstance(failure, dict) else None
        if failed_on is None:
            problems.append(f"{where}: last_registry_failure must record an ISO date under 'on'")

    projects = document.get("projects")
    if not isinstance(projects, list):
        raise Refusal(f"{where}: 'projects' must be a list")
    entries = [entry for entry in projects if isinstance(entry, dict)]
    recorded = {entry.get("name"): entry for entry in entries}
    if len(recorded) != len(entries):
        problems.append("publisher confirmations contain duplicate project names")
    missing = sorted(set(manifest.names) - set(recorded))
    extra = sorted(set(recorded) - set(manifest.names))
    if missing:
        problems.append(f"no publisher confirmation recorded for {missing}")
    if extra:
        problems.append(f"publisher confirmations for unknown projects: {extra}")

    for name in sorted(set(manifest.names) & set(recorded)):
        entry = recorded[name]
        if entry.get("publisher_environment") != BOOTSTRAP_ENVIRONMENTS.get(name):
            problems.append(f"{name}: publisher_environment does not match the bootstrap identity")
        if entry.get("publisher_project") != name:
            problems.append(
                f"{name}: Trusted Publisher project name must be recorded exactly "
                f"as {name!r}, found {entry.get('publisher_project')!r}"
            )
            continue
        if name not in required:
            continue
        kind = entry.get("publisher_kind")
        if kind not in PUBLISHER_KINDS:
            problems.append(
                f"{name}: publisher_kind must be one of {sorted(PUBLISHER_KINDS)}, found {kind!r}"
            )
        elif entry.get("pypi_state") != PUBLISHER_KINDS[kind]:
            problems.append(
                f"{name}: a {kind} publisher belongs to a project that is "
                f"{PUBLISHER_KINDS[kind]} on PyPI, but pypi_state records "
                f"{entry.get('pypi_state')!r}"
            )
        if entry.get("trusted_publisher") != VERIFIED:
            problems.append(
                f"{name}: trusted_publisher is not {VERIFIED}; the owner must read back "
                f"the {kind or 'pending or active'} publisher and record {VERIFIED}"
            )
            continue
        confirmation = _confirmation_problems(
            entry.get("verified_by"), entry.get("verified_on"), subject=name
        )
        problems.extend(confirmation)
        verified_on = _iso_date(entry.get("verified_on"))
        if (
            not confirmation
            and failed_on is not None
            and verified_on is not None
            and verified_on < failed_on
        ):
            problems.append(
                f"{name}: the readback of {verified_on.isoformat()} predates the registry "
                f"failure of {failed_on.isoformat()}; read the publisher back again"
            )
    return problems


def publisher_kinds(workspace: Path) -> dict[str, str]:
    """Project name -> recorded publisher kind, for the online consistency check."""
    document = load_publication_record(workspace)
    projects = document.get("projects")
    if not isinstance(projects, list):
        return {}
    return {
        entry["name"]: entry["publisher_kind"]
        for entry in projects
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and entry.get("publisher_kind") in PUBLISHER_KINDS
    }


def check_workflow_identity(workspace: Path) -> list[str]:
    """The recorded tuple must be one this repository can actually present.

    PyPI matches the OIDC token against the publisher's workflow filename and
    environment name. A record that names a workflow file that does not exist,
    or an environment no publishing job enters, is a record of nothing.
    """
    workflow = REQUIRED_PUBLISHER["workflow"]
    environment = AUTHORIZATION_ENVIRONMENT
    path = workspace / WORKFLOWS_RELATIVE / workflow
    if not path.is_file():
        return [f"{WORKFLOWS_RELATIVE.as_posix()}/{workflow} does not exist"]
    text = path.read_text(encoding="utf-8")
    pattern = rf"^\s*environment:\s*\n\s*name:\s*{re.escape(environment)}\s*$"
    if not re.search(pattern, text, re.M):
        return [f"{workflow} has no job that runs in the {environment!r} environment"]
    problems: list[str] = []
    for project, expected in BOOTSTRAP_ENVIRONMENTS.items():
        job = "publish-" + expected.removeprefix("pypi-")
        body = re.search(rf"^  {re.escape(job)}:\n(.*?)(?=^  [\w-]+:|\Z)", text, re.M | re.S)
        if body is None or not re.search(
            rf"^    environment:\n      name: {re.escape(expected)}\s*$",
            body.group(1),
            re.M,
        ):
            problems.append(f"{project}: {workflow} must run {job} in {expected}")
    return problems


def check_oidc_identity(
    environ: Mapping[str, str], *, project: str | None = None, environment: str | None = None
) -> list[str]:
    """Inside GitHub Actions: this run *is* the recorded Trusted Publisher.

    `GITHUB_REPOSITORY` and `GITHUB_WORKFLOW_REF` are what the OIDC token will
    carry as `repository` and `workflow_ref`. If they do not spell the recorded
    tuple, PyPI will refuse the upload whatever the record says, so refuse
    here, before any tag exists.
    """
    owner = REQUIRED_PUBLISHER["owner"]
    repository = REQUIRED_PUBLISHER["repository"]
    workflow = REQUIRED_PUBLISHER["workflow"]
    expected_repository = f"{owner}/{repository}"
    expected_prefix = f"{expected_repository}/{WORKFLOWS_RELATIVE.as_posix()}/{workflow}@"

    actual_repository = environ.get("GITHUB_REPOSITORY")
    actual_workflow = environ.get("GITHUB_WORKFLOW_REF")
    if not actual_repository or not actual_workflow:
        return ["the OIDC identity can only be checked inside a GitHub Actions run"]
    problems: list[str] = []
    if actual_repository != expected_repository:
        problems.append(
            f"this run belongs to {actual_repository}, the recorded publisher is "
            f"{expected_repository}"
        )
    if actual_workflow != expected_prefix + "refs/heads/main":
        problems.append(
            f"this run's workflow is {actual_workflow.split('@', 1)[0]}, the recorded publisher "
            f"is {expected_prefix.rstrip('@')}"
        )
    if project is not None or environment is not None:
        expected_environment = BOOTSTRAP_ENVIRONMENTS.get(project or "")
        if expected_environment is None or environment != expected_environment:
            problems.append("distribution/environment does not match the bootstrap identity")
        else:
            expected_job = "publish-" + expected_environment.removeprefix("pypi-")
            if environ.get("GITHUB_JOB") != expected_job:
                problems.append("this job is not the distribution's bootstrap publishing job")
    elif (
        environ.get("GITHUB_JOB", "").startswith("publish-")
        and environ.get("GITHUB_JOB") != "publish-preflight"
    ):
        problems.append("a bootstrap upload must specify its project and environment")
    return problems


def _index_json(index: str, name: str) -> dict[str, Any] | None:
    """The project's JSON document, or None when the project does not exist."""
    request = urllib.request.Request(
        f"{index}/pypi/{name}/json",
        headers={"Accept": "application/json", "User-Agent": "agnara-release-check"},
    )
    try:
        with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise Refusal(f"{_safe_url_for_log(index)} returned HTTP {exc.code} for {name}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise Refusal(
            f"cannot query {_safe_url_for_log(index)} for {name}: {sanitize_for_log(exc)}"
        ) from exc


def check_index(
    manifest: distributions.Manifest,
    version: str,
    *,
    index: str,
    require_published: bool,
    recorded_kinds: Mapping[str, str] | None = None,
    phase: str | None = None,
) -> tuple[list[str], list[str]]:
    """Compare the index against what this release intends to put there.

    Before publishing, nothing of this version may exist -- a rerun over an
    existing file is what `skip-existing` would hide -- and the publisher kind
    the record claims to have read back must agree with whether the project
    exists: a pending publisher on an existing project, or an active one on a
    project that is not there, is a readback of the wrong page. Afterwards,
    every one of the seven must carry both a wheel and an sdist, which is
    precisely what `0.1.0a4` failed to do even for the one project it reached.

    With a ``phase``, "nothing may exist" applies to the projects this phase
    and later phases upload, while the projects of earlier phases must
    already be *complete* -- the proof that the earlier phase happened. After
    the phase, completeness is required for everything published so far, and
    the projects of later phases must still be untouched.
    """
    problems: list[str] = []
    notes: list[str] = []
    safe_index = _safe_url_for_log(index)
    kinds = recorded_kinds or {}
    earlier = set(projects_published_before(phase)) if phase is not None else set()
    complete_after = (
        set(projects_published_through(phase)) if phase is not None else set(manifest.names)
    )
    for distribution in manifest.distributions:
        name = distribution.name
        document = _index_json(index, name)
        kind = kinds.get(name)
        # An earlier phase consumed this project's pending publisher; its
        # record now describes the past, and the index is the evidence.
        if not require_published and kind is not None and name not in earlier:
            actual = "absent" if document is None else "existing"
            if PUBLISHER_KINDS[kind] != actual:
                problems.append(
                    f"{name}: the record read back a publisher of kind {kind!r}, but the "
                    f"project is {actual} on {safe_index}; re-verify it where PyPI actually "
                    "holds it"
                )
        must_be_complete = name in complete_after if require_published else name in earlier
        if document is None:
            if must_be_complete:
                stage = "after publication" if require_published else "before this phase"
                problems.append(f"{name}: no project on {safe_index} {stage}")
            elif require_published:
                notes.append(f"{name}: not published yet, as this phase intends")
            else:
                notes.append(
                    f"{name}: no project yet; the first upload must be created by a "
                    "pending Trusted Publisher"
                )
            continue

        files = [file["filename"] for file in document.get("releases", {}).get(version, [])]
        if must_be_complete:
            stem = distribution.artifact_stem
            wanted = {f"{stem}-{version}-py3-none-any.whl", f"{stem}-{version}.tar.gz"}
            absent = sorted(wanted - set(files))
            if absent:
                problems.append(f"{name} {version} is incomplete on {safe_index}; missing {absent}")
            else:
                notes.append(f"{name} {version}: wheel and sdist present")
        elif files:
            problems.append(
                f"{name} {version} already has {len(files)} file(s) on {safe_index}: "
                f"{sorted(files)}. "
                "PyPI files are immutable; select the next version rather than republishing"
            )
        else:
            notes.append(f"{name}: project exists, {version} not yet uploaded")
    return problems, notes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(
    workspace: Path,
    version: str,
    *,
    dist_dir: Path | None,
    tag: str | None,
    online: bool,
    require_published: bool,
    index: str,
    oidc_identity: bool = False,
    environ: Mapping[str, str] | None = None,
    project: str | None = None,
    environment: str | None = None,
    phase: str | None = None,
) -> tuple[int, list[str], list[str]]:
    if VERSION_PATTERN.fullmatch(version) is None:
        return (
            1,
            [f"{version!r} is not a publishable release version"],
            ["publication readiness requires an exact public release version"],
        )

    manifest = distributions.load(workspace)
    problems: list[str] = []
    notes = [
        f"reviewed publication set: {len(manifest.distributions)} distributions "
        f"({', '.join(manifest.names)})",
        f"upload order, kernel last: {' -> '.join(manifest.publication_order)}",
    ]
    if phase is not None:
        uploads = phase_projects(phase)
        notes.append(
            f"phase {phase}: uploads {', '.join(uploads)}; already published before it: "
            f"{', '.join(projects_published_before(phase)) or 'nothing'}"
        )
        if project is not None and project not in uploads:
            problems.append(f"{project} is not uploaded by phase {phase}")

    problems.extend(check_workspace(workspace, manifest, version))
    problems.extend(check_no_stale_versions(workspace, manifest, version))
    problems.extend(check_release_notes(workspace, version))
    problems.extend(check_changelog(workspace, version))
    problems.extend(check_publisher_record(workspace, manifest, phase=phase))
    problems.extend(check_workflow_identity(workspace))
    problems.extend(check_tag(workspace, version, tag))

    if oidc_identity:
        problems.extend(
            check_oidc_identity(
                os.environ if environ is None else environ, project=project, environment=environment
            )
        )
        if not problems:
            notes.append("this run presents the recorded Trusted Publisher identity")
    elif project is not None or environment is not None:
        problems.append("project/environment requires --oidc-identity")

    if dist_dir is not None:
        problems.extend(check_artifact_set(manifest, dist_dir, version))
        notes.append(f"artifact set checked in {dist_dir}")

    if online:
        index_problems, index_notes = check_index(
            manifest,
            version,
            index=index,
            require_published=require_published,
            recorded_kinds=publisher_kinds(workspace),
            phase=phase,
        )
        problems.extend(index_problems)
        notes.extend(index_notes)

    return (1 if problems else 0), problems, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="the release version being published")
    parser.add_argument(
        "--phase",
        choices=PHASE_ORDER,
        default=None,
        help="the bootstrap phase being run; requires readbacks and index state for it only",
    )
    parser.add_argument("--project", help="canonical distribution being uploaded by this job")
    parser.add_argument("--environment", help="this upload job's bootstrap OIDC environment")
    parser.add_argument("--workspace", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--dist", type=Path, default=None, help="also check this artifact set")
    parser.add_argument("--tag", default=None, help="also check this annotated tag")
    parser.add_argument(
        "--online", action="store_true", help="also query the package index (needs network)"
    )
    parser.add_argument(
        "--require-published",
        action="store_true",
        help="with --online, require every distribution to be complete on the index",
    )
    parser.add_argument("--index", default=DEFAULT_INDEX, help=f"index base URL ({DEFAULT_INDEX})")
    parser.add_argument(
        "--oidc-identity",
        action="store_true",
        help="inside GitHub Actions, require this run to be the recorded Trusted Publisher",
    )
    arguments = parser.parse_args(argv)

    try:
        code, problems, notes = run(
            arguments.workspace.resolve(),
            arguments.version,
            dist_dir=arguments.dist,
            tag=arguments.tag,
            online=arguments.online,
            require_published=arguments.require_published,
            index=arguments.index,
            oidc_identity=arguments.oidc_identity,
            project=arguments.project,
            environment=arguments.environment,
            phase=arguments.phase,
        )
    except (Refusal, distributions.ManifestError) as exc:
        _emit_error(f"publication readiness could not be evaluated: {exc}")
        return 2

    for note in notes:
        _emit(note)
    for problem in problems:
        _emit_error(problem)
    verdict = "NOT READY" if code else "READY"
    where = PUBLICATION_RELATIVE.as_posix()
    confirmed = "" if code else f" (registry configuration confirmed in {where})"
    _emit(f"PUBLISH {verdict} for {arguments.version}{confirmed}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
