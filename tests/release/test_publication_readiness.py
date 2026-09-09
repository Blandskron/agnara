"""`scripts/check_publication_readiness.py` is the gate `0.1.0a4` did not have.

Its whole value is that it says no. These tests hold the refusals that matter:
an unconfirmed Trusted Publisher, a readback older than the last registry
failure, a confirmation signed by an automation identity, a publisher kind that
disagrees with whether the project exists, a recorded tuple this repository's
workflow cannot present, a distribution left behind at another version, an
adapter whose core pin drifted, a missing release note, an incomplete artifact
set, and a version that already exists on the index.

A gate that can only pass is not a gate, so every case below constructs the
failure and asserts the script reports it.
"""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

import distributions
from tests.architecture.boundaries import WORKSPACE_ROOT

VERSION = "9.9.9a1"
READBACK = "2026-09-09"
FAILURE = "2026-09-08"
OWNER = "owner"


def _load() -> Any:
    location = WORKSPACE_ROOT / "scripts" / "check_publication_readiness.py"
    spec = importlib.util.spec_from_file_location("agnara_publication_readiness", location)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load()
MANIFEST = distributions.load(WORKSPACE_ROOT)

ACTIONS_ENVIRON = {
    "GITHUB_REPOSITORY": "Blandskron/agnara",
    "GITHUB_WORKFLOW_REF": "Blandskron/agnara/.github/workflows/release.yml@refs/heads/main",
}


# ---------------------------------------------------------------------------
# A synthetic workspace that starts out publishable
# ---------------------------------------------------------------------------


def _package(root: Path, distribution: distributions.Distribution, version: str) -> None:
    package = root / "packages" / distribution.name
    (package / "src" / distribution.import_name).mkdir(parents=True)
    (package / "src" / distribution.import_name / "__init__.py").touch()

    lines = [
        "[project]",
        f'name = "{distribution.name}"',
        f'version = "{version}"',
    ]
    requirements = list(distribution.third_party_requirements)
    if distribution.name != MANIFEST.core:
        requirements.insert(0, f"{MANIFEST.core}=={version}")
    rendered = ", ".join(f'"{requirement}"' for requirement in requirements)
    lines.append(f"dependencies = [{rendered}]")
    if distribution.console_scripts:
        lines.append("")
        lines.append("[project.scripts]")
        lines.extend(
            f'{script} = "{distribution.import_name}._main:main"'
            for script in distribution.console_scripts
        )
    (package / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_workflow(root: Path, *, environment: str | None = "pypi") -> None:
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    body = "jobs:\n  publish:\n"
    if environment is not None:
        body += f"    environment:\n      name: {environment}\n"
    body += "    steps: []\n"
    for expected in tool.BOOTSTRAP_ENVIRONMENTS.values():
        job = "publish-" + expected.removeprefix("pypi-")
        body += f"  {job}:\n    environment:\n      name: {expected}\n    steps: []\n"
    (workflows / "release.yml").write_text(body, encoding="utf-8")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A minimal checkout the tool accepts, so a test can break one thing."""
    root = tmp_path / "checkout"
    (root / "docs" / "releases").mkdir(parents=True)
    shutil.copy(WORKSPACE_ROOT / "docs" / "distributions.json", root / "docs")

    for distribution in MANIFEST.distributions:
        _package(root, distribution, VERSION)

    locked = "\n".join(
        f'[[package]]\nname = "{name}"\nversion = "{VERSION}"\n' for name in MANIFEST.names
    )
    (root / "uv.lock").write_text(locked, encoding="utf-8")

    (root / "docs" / "releases" / f"v{VERSION}.md").write_text(
        f"# Agnara v{VERSION}\n", encoding="utf-8"
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [Unreleased]\n\n## [{VERSION}] - 2026-09-08\n\n- something\n\n"
        f"[{VERSION}]: https://github.com/Blandskron/agnara/compare/v0.1.0a4...v{VERSION}\n",
        encoding="utf-8",
    )
    _write_workflow(root)
    _write_publication(root, {})
    return root


def _project(name: str, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "publisher_project": name,
        "publisher_environment": tool.BOOTSTRAP_ENVIRONMENTS[name],
        "publisher_kind": "active" if name == MANIFEST.core else "pending",
        "pypi_state": "existing" if name == MANIFEST.core else "absent",
        "trusted_publisher": "VERIFIED",
        "verified_by": OWNER,
        "verified_on": READBACK,
    }
    entry.update(overrides)
    return entry


def _projects(**overrides: Any) -> list[dict[str, Any]]:
    return [_project(name, **overrides) for name in MANIFEST.names]


def _write_publication(root: Path, overrides: dict[str, Any]) -> None:
    document: dict[str, Any] = {
        "schema_version": tool.SCHEMA_VERSION,
        "publisher": dict(tool.REQUIRED_PUBLISHER),
        "release_authorization": {
            "mechanism": tool.AUTHORIZATION_MECHANISM,
            "environment": tool.AUTHORIZATION_ENVIRONMENT,
        },
        "status": "VERIFIED",
        "confirmed_by": OWNER,
        "confirmed_on": READBACK,
        "last_registry_failure": {"version": "0.1.0a6", "on": FAILURE},
        "projects": _projects(),
    }
    document.update(overrides)
    (root / "docs" / "releases" / "publication.json").write_text(
        json.dumps(document), encoding="utf-8"
    )


def _run(workspace: Path, **kwargs: Any) -> tuple[int, list[str]]:
    code, problems, _ = tool.run(
        workspace,
        kwargs.pop("version", VERSION),
        dist_dir=kwargs.pop("dist_dir", None),
        tag=kwargs.pop("tag", None),
        online=False,
        require_published=False,
        index=tool.DEFAULT_INDEX,
        oidc_identity=kwargs.pop("oidc_identity", False),
        environ=kwargs.pop("environ", {}),
        project=kwargs.pop("project", None),
        environment=kwargs.pop("environment", None),
        phase=kwargs.pop("phase", None),
    )
    assert not kwargs
    return code, problems


# ---------------------------------------------------------------------------
# The happy path exists, so the refusals below mean something
# ---------------------------------------------------------------------------


def test_a_complete_workspace_is_publish_ready(workspace: Path) -> None:
    code, problems = _run(workspace)

    assert (code, problems) == (0, [])


def test_the_real_repository_is_evaluated_without_crashing() -> None:
    """Whatever the answer is, the tool must be able to reach one here."""
    code, problems, notes = tool.run(
        WORKSPACE_ROOT,
        distributions.load(WORKSPACE_ROOT) and _repository_version(),
        dist_dir=None,
        tag=None,
        online=False,
        require_published=False,
        index=tool.DEFAULT_INDEX,
    )

    assert code in (0, 1)
    assert notes
    assert isinstance(problems, list)


def _repository_version() -> str:
    import tomllib

    path = WORKSPACE_ROOT / "packages" / "agnara" / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"]


# ---------------------------------------------------------------------------
# The committed record itself
# ---------------------------------------------------------------------------


def _committed_record() -> dict[str, Any]:
    return json.loads(
        (WORKSPACE_ROOT / "docs" / "releases" / "publication.json").read_text(encoding="utf-8")
    )


def test_the_committed_record_names_every_project_by_its_canonical_name() -> None:
    """`agnara_a2a` is a filename, not a project. The record never says it."""
    document = _committed_record()
    recorded = {entry["name"]: entry["publisher_project"] for entry in document["projects"]}

    assert document["schema_version"] == tool.SCHEMA_VERSION
    assert sorted(recorded) == sorted(MANIFEST.names)
    for name, publisher_project in recorded.items():
        assert publisher_project == name
        assert "_" not in publisher_project


def test_the_committed_record_delegates_authorization_to_the_pypi_environment() -> None:
    document = _committed_record()

    assert document["publisher"] == tool.REQUIRED_PUBLISHER
    assert document["release_authorization"]["mechanism"] == tool.AUTHORIZATION_MECHANISM
    assert document["release_authorization"]["environment"] == "pypi"
    assert "target" not in document, "authorization is no longer a per-target JSON edit"
    assert all("verified_for_target" not in entry for entry in document["projects"])


def test_the_committed_record_describes_a_workflow_this_repository_has() -> None:
    assert tool.check_workflow_identity(WORKSPACE_ROOT) == []


# ---------------------------------------------------------------------------
# The registry contract
# ---------------------------------------------------------------------------


def test_an_unverified_trusted_publisher_refuses_the_release(workspace: Path) -> None:
    """This single case is the whole `0.1.0a4` incident."""
    _write_publication(workspace, {"projects": _projects(trusted_publisher="UNVERIFIED")})

    code, problems = _run(workspace)

    assert code == 1
    assert len(problems) == len(MANIFEST.names)
    assert all("trusted_publisher is not VERIFIED" in problem for problem in problems)


def test_top_level_confirmation_is_required(workspace: Path) -> None:
    _write_publication(workspace, {"status": "UNVERIFIED"})

    code, problems = _run(workspace)

    assert code == 1
    assert any("top-level status is not VERIFIED" in problem for problem in problems)


def test_pending_publisher_project_name_must_be_exact(workspace: Path) -> None:
    projects = [
        _project(name, publisher_project="agnara_a2a" if name == "agnara-a2a" else name)
        for name in MANIFEST.names
    ]
    _write_publication(workspace, {"projects": projects})

    code, problems = _run(workspace)

    assert code == 1
    assert any(
        "project name must be recorded exactly as 'agnara-a2a'" in problem for problem in problems
    )


def test_duplicate_publisher_project_records_are_rejected(workspace: Path) -> None:
    projects = _projects()
    projects.append(dict(projects[0]))
    _write_publication(workspace, {"projects": projects})

    code, problems = _run(workspace)

    assert code == 1
    assert any("duplicate project names" in problem for problem in problems)


def test_a_readback_older_than_the_last_registry_failure_is_refused(workspace: Path) -> None:
    """`0.1.0a6` proved a readback wrong. Everything read before it is void."""
    _write_publication(workspace, {"projects": _projects(verified_on="2026-09-07")})

    code, problems = _run(workspace)

    assert code == 1
    assert len(problems) == len(MANIFEST.names)
    assert all("predates the registry failure of 2026-09-08" in problem for problem in problems)


def test_a_readback_on_the_day_of_the_failure_or_later_is_accepted(workspace: Path) -> None:
    _write_publication(workspace, {"projects": _projects(verified_on=FAILURE)})

    assert _run(workspace) == (0, [])


def test_a_confirmation_must_name_who_made_it(workspace: Path) -> None:
    _write_publication(workspace, {"projects": _projects(verified_by=None, verified_on=None)})

    code, problems = _run(workspace)

    assert code == 1
    assert all("who verified it and when" in problem for problem in problems)


@pytest.mark.parametrize(
    "identity",
    ["github-actions[bot]", "release workflow", "codex", "Claude", "dependabot", "an agent"],
)
def test_an_automation_identity_cannot_confirm_a_publisher(workspace: Path, identity: str) -> None:
    """The pipeline must never be able to certify its own registry configuration."""
    _write_publication(workspace, {"projects": _projects(verified_by=identity)})

    code, problems = _run(workspace)

    assert code == 1
    assert all("names an automation identity" in problem for problem in problems)


def test_an_automation_identity_cannot_confirm_the_record_as_a_whole(workspace: Path) -> None:
    _write_publication(workspace, {"confirmed_by": "github-actions[bot]"})

    code, problems = _run(workspace)

    assert code == 1
    assert any("names an automation identity" in problem for problem in problems)


def test_a_confirmation_date_must_be_a_real_date(workspace: Path) -> None:
    _write_publication(workspace, {"projects": _projects(verified_on="yesterday")})

    code, problems = _run(workspace)

    assert code == 1
    assert all("must be an ISO date" in problem for problem in problems)


def test_a_missing_project_confirmation_is_not_silently_skipped(workspace: Path) -> None:
    projects = [entry for entry in _projects() if entry["name"] != "agnara-mcp"]
    _write_publication(workspace, {"projects": projects})

    code, problems = _run(workspace)

    assert code == 1
    assert any("no publisher confirmation recorded for ['agnara-mcp']" in p for p in problems)


def test_a_different_publisher_tuple_is_refused(workspace: Path) -> None:
    """A tuple that differs in any field is a different identity to PyPI."""
    publisher = dict(tool.REQUIRED_PUBLISHER) | {"environment": "release"}
    _write_publication(workspace, {"publisher": publisher})

    code, problems = _run(workspace)

    assert code == 1
    assert any("publisher tuple does not match" in problem for problem in problems)


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        {"mechanism": "publication.json", "environment": "pypi"},
        {"mechanism": "github-environment", "environment": "release"},
    ],
)
def test_release_authorization_must_be_the_pypi_environment(
    workspace: Path, authorization: dict[str, str] | None
) -> None:
    """A human authorizes a release by approving the environment, never by a JSON edit."""
    _write_publication(workspace, {"release_authorization": authorization})

    code, problems = _run(workspace)

    assert code == 1
    assert any("release_authorization must be the github-environment 'pypi'" in p for p in problems)


def test_a_publisher_kind_that_disagrees_with_the_recorded_pypi_state_is_refused(
    workspace: Path,
) -> None:
    """Pending publishers live on the account page, active ones on the project."""
    projects = [
        _project(name, publisher_kind="pending") if name == MANIFEST.core else _project(name)
        for name in MANIFEST.names
    ]
    _write_publication(workspace, {"projects": projects})

    code, problems = _run(workspace)

    assert code == 1
    assert any(
        "agnara: a pending publisher belongs to a project that is absent on PyPI" in p
        for p in problems
    )


def test_an_unknown_publisher_kind_is_refused(workspace: Path) -> None:
    _write_publication(workspace, {"projects": _projects(publisher_kind="trusted")})

    code, problems = _run(workspace)

    assert code == 1
    assert all("publisher_kind must be one of ['active', 'pending']" in p for p in problems)


def test_a_malformed_registry_failure_record_is_refused(workspace: Path) -> None:
    _write_publication(workspace, {"last_registry_failure": {"version": "0.1.0a6"}})

    code, problems = _run(workspace)

    assert code == 1
    assert any("last_registry_failure must record an ISO date" in p for p in problems)


def test_a_record_without_a_registry_failure_is_still_acceptable(workspace: Path) -> None:
    _write_publication(workspace, {"last_registry_failure": None})

    assert _run(workspace) == (0, [])


# ---------------------------------------------------------------------------
# The recorded tuple must be one this repository can present
# ---------------------------------------------------------------------------


def test_the_recorded_workflow_must_run_a_job_in_the_publisher_environment(
    workspace: Path,
) -> None:
    _write_workflow(workspace, environment="release")

    code, problems = _run(workspace)

    assert code == 1
    assert any("no job that runs in the 'pypi' environment" in p for p in problems)


def test_a_missing_release_workflow_is_refused(workspace: Path) -> None:
    (workspace / ".github" / "workflows" / "release.yml").unlink()

    code, problems = _run(workspace)

    assert code == 1
    assert any("release.yml does not exist" in p for p in problems)


def test_the_running_workflow_must_be_the_recorded_publisher(workspace: Path) -> None:
    assert _run(workspace, oidc_identity=True, environ=ACTIONS_ENVIRON) == (0, [])


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, "can only be checked inside a GitHub Actions run"),
        (
            ACTIONS_ENVIRON | {"GITHUB_REPOSITORY": "someone/agnara"},
            "this run belongs to someone/agnara",
        ),
        (
            ACTIONS_ENVIRON
            | {"GITHUB_WORKFLOW_REF": "Blandskron/agnara/.github/workflows/ci.yml@refs/heads/main"},
            "this run's workflow is Blandskron/agnara/.github/workflows/ci.yml",
        ),
    ],
)
def test_a_run_that_is_not_the_recorded_publisher_is_refused(
    workspace: Path, environ: dict[str, str], expected: str
) -> None:
    """PyPI would refuse the upload; refusing here happens before any tag exists."""
    code, problems = _run(workspace, oidc_identity=True, environ=environ)

    assert code == 1
    assert any(expected in problem for problem in problems)


def test_the_oidc_identity_is_not_required_outside_the_workflow(workspace: Path) -> None:
    assert _run(workspace, oidc_identity=False, environ={}) == (0, [])


@pytest.mark.parametrize("project,environment", tool.BOOTSTRAP_ENVIRONMENTS.items())
def test_bootstrap_upload_refuses_every_other_distribution_identity(
    project: str,
    environment: str,
) -> None:
    job = "publish-" + environment.removeprefix("pypi-")
    context = ACTIONS_ENVIRON | {"GITHUB_JOB": job}
    assert tool.check_oidc_identity(context, project=project, environment=environment) == []
    assert tool.check_oidc_identity(context)  # an upload cannot omit its identity
    for other in {*tool.BOOTSTRAP_ENVIRONMENTS.values(), "pypi"} - {environment}:
        assert tool.check_oidc_identity(context, project=project, environment=other)
    assert tool.check_oidc_identity(
        context | {"GITHUB_JOB": "publish"}, project=project, environment=environment
    )
    assert tool.check_oidc_identity(
        context
        | {
            "GITHUB_WORKFLOW_REF": ACTIONS_ENVIRON["GITHUB_WORKFLOW_REF"].replace(
                "/main", "/develop"
            )
        },
        project=project,
        environment=environment,
    )


def test_old_common_publisher_readback_cannot_certify_bootstrap(workspace: Path) -> None:
    _write_publication(workspace, {"projects": _projects(publisher_environment="pypi")})
    code, problems = _run(workspace)
    assert code == 1
    assert sum("publisher_environment" in problem for problem in problems) == 7


def test_wrong_bootstrap_environment_in_workflow_fails_offline(workspace: Path) -> None:
    path = workspace / ".github/workflows/release.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("name: pypi-cli", "name: pypi-a2a"),
        encoding="utf-8",
    )
    assert any("agnara-cli" in problem for problem in tool.check_workflow_identity(workspace))


# ---------------------------------------------------------------------------
# Version identity across the seven
# ---------------------------------------------------------------------------


def test_one_distribution_left_behind_is_refused(workspace: Path) -> None:
    path = workspace / "packages" / "agnara-http" / "pyproject.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(f'version = "{VERSION}"', 'version = "0.0.1a1"'),
        encoding="utf-8",
    )

    code, problems = _run(workspace)

    assert code == 1
    assert any("agnara-http: declares 0.0.1a1" in problem for problem in problems)


def test_an_adapter_whose_core_pin_drifted_is_refused(workspace: Path) -> None:
    path = workspace / "packages" / "agnara-cli" / "pyproject.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(f"agnara=={VERSION}", "agnara>=0.1"),
        encoding="utf-8",
    )

    code, problems = _run(workspace)

    assert code == 1
    assert any("must pin agnara==" in problem for problem in problems)


def test_a_stale_lockfile_entry_is_refused(workspace: Path) -> None:
    lock = workspace / "uv.lock"
    lock.write_text(
        lock.read_text(encoding="utf-8").replace(
            f'name = "agnara-mcp"\nversion = "{VERSION}"',
            'name = "agnara-mcp"\nversion = "0.0.1a1"',
        ),
        encoding="utf-8",
    )

    code, problems = _run(workspace)

    assert code == 1
    assert any("uv.lock records versions other than" in problem for problem in problems)


def test_a_development_version_is_not_publishable(workspace: Path) -> None:
    code, problems = _run(workspace, version=f"{VERSION}.dev0")

    assert code == 1
    assert any("not a publishable" in problem for problem in problems)


# ---------------------------------------------------------------------------
# Release notes
# ---------------------------------------------------------------------------


def test_missing_release_notes_are_refused_rather_than_degraded(workspace: Path) -> None:
    """`release.yml` used to fall back to the generated PR list without saying so."""
    (workspace / "docs" / "releases" / f"v{VERSION}.md").unlink()

    code, problems = _run(workspace)

    assert code == 1
    assert any("is missing" in problem for problem in problems)


def test_release_notes_that_never_name_the_version_are_refused(workspace: Path) -> None:
    (workspace / "docs" / "releases" / f"v{VERSION}.md").write_text("# notes\n", encoding="utf-8")

    code, problems = _run(workspace)

    assert code == 1
    assert any("never names" in problem for problem in problems)


def test_an_unclosed_changelog_is_refused(workspace: Path) -> None:
    (workspace / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")

    code, problems = _run(workspace)

    assert code == 1
    assert any("no dated" in problem for problem in problems)
    assert any("no comparison link" in problem for problem in problems)


# ---------------------------------------------------------------------------
# The built artifact set
# ---------------------------------------------------------------------------


def _dist(root: Path, *, omit: str | None = None, extra: str | None = None) -> Path:
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    for distribution in MANIFEST.distributions:
        stem = distribution.artifact_stem
        for name in (f"{stem}-{VERSION}-py3-none-any.whl", f"{stem}-{VERSION}.tar.gz"):
            if name == omit:
                continue
            (dist / name).write_bytes(b"")
    if extra:
        (dist / extra).write_bytes(b"")
    return dist


def test_a_complete_artifact_set_is_accepted(workspace: Path) -> None:
    code, problems = _run(workspace, dist_dir=_dist(workspace))

    assert (code, problems) == (0, [])


def test_a_missing_sdist_is_refused(workspace: Path) -> None:
    """`agnara 0.1.0a4` is a wheel with no sdist. This is that condition."""
    dist = _dist(workspace, omit=f"agnara-{VERSION}.tar.gz")

    code, problems = _run(workspace, dist_dir=dist)

    assert code == 1
    assert any(f"agnara-{VERSION}.tar.gz" in problem for problem in problems)


def test_an_unreviewed_artifact_is_refused(workspace: Path) -> None:
    dist = _dist(workspace, extra=f"agnara_secret-{VERSION}-py3-none-any.whl")

    code, problems = _run(workspace, dist_dir=dist)

    assert code == 1
    assert any("unreviewed files" in problem for problem in problems)


# ---------------------------------------------------------------------------
# The index, with the network stubbed
# ---------------------------------------------------------------------------


def _stub_index(monkeypatch: pytest.MonkeyPatch, responses: dict[str, Any]) -> None:
    monkeypatch.setattr(tool, "_index_json", lambda index, name: responses.get(name))


def test_a_version_already_on_the_index_stops_the_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PyPI files are immutable, so this is not a condition to skip past."""
    _stub_index(
        monkeypatch,
        {"agnara": {"releases": {VERSION: [{"filename": f"agnara-{VERSION}-py3-none-any.whl"}]}}},
    )

    problems, notes = tool.check_index(
        MANIFEST, VERSION, index=tool.DEFAULT_INDEX, require_published=False
    )

    assert any("already has 1 file" in problem for problem in problems)
    assert any("pending Trusted Publisher" in note for note in notes)


def test_a_project_that_does_not_exist_yet_is_reported_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_index(monkeypatch, {})

    problems, notes = tool.check_index(
        MANIFEST, VERSION, index=tool.DEFAULT_INDEX, require_published=False
    )

    assert problems == []
    assert len(notes) == len(MANIFEST.names)


def test_a_pending_publisher_recorded_for_an_existing_project_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The readback looked at the account page for a project that has its own."""
    _stub_index(monkeypatch, {"agnara": {"releases": {}}})

    problems, _ = tool.check_index(
        MANIFEST,
        VERSION,
        index=tool.DEFAULT_INDEX,
        require_published=False,
        recorded_kinds={"agnara": "pending"},
    )

    assert problems == [
        "agnara: the record read back a publisher of kind 'pending', but the project is "
        "existing on https://pypi.org; re-verify it where PyPI actually holds it"
    ]


def test_an_active_publisher_recorded_for_an_absent_project_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No project, no active publisher: it is a pending one or nothing."""
    _stub_index(monkeypatch, {})

    problems, _ = tool.check_index(
        MANIFEST,
        VERSION,
        index=tool.DEFAULT_INDEX,
        require_published=False,
        recorded_kinds={"agnara-a2a": "active"},
    )

    assert problems == [
        "agnara-a2a: the record read back a publisher of kind 'active', but the project is "
        "absent on https://pypi.org; re-verify it where PyPI actually holds it"
    ]


def test_consistent_publisher_kinds_pass_the_index_check(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_index(monkeypatch, {"agnara": {"releases": {}}})
    kinds = {name: ("active" if name == "agnara" else "pending") for name in MANIFEST.names}

    problems, _ = tool.check_index(
        MANIFEST, VERSION, index=tool.DEFAULT_INDEX, require_published=False, recorded_kinds=kinds
    )

    assert problems == []


def test_post_publication_requires_a_wheel_and_an_sdist_for_every_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact `0.1.0a4` end state: one project, wheel only, siblings absent."""
    _stub_index(
        monkeypatch,
        {"agnara": {"releases": {VERSION: [{"filename": f"agnara-{VERSION}-py3-none-any.whl"}]}}},
    )

    problems, _ = tool.check_index(
        MANIFEST, VERSION, index=tool.DEFAULT_INDEX, require_published=True
    )

    assert any(f"missing ['agnara-{VERSION}.tar.gz']" in problem for problem in problems)
    assert sum("no project on" in problem for problem in problems) == len(MANIFEST.names) - 1


def test_a_complete_index_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_index(
        monkeypatch,
        {
            distribution.name: {
                "releases": {
                    VERSION: [
                        {"filename": f"{distribution.artifact_stem}-{VERSION}-py3-none-any.whl"},
                        {"filename": f"{distribution.artifact_stem}-{VERSION}.tar.gz"},
                    ]
                }
            }
            for distribution in MANIFEST.distributions
        },
    )

    problems, notes = tool.check_index(
        MANIFEST, VERSION, index=tool.DEFAULT_INDEX, require_published=True
    )

    assert problems == []
    assert len(notes) == len(MANIFEST.names)


# ---------------------------------------------------------------------------
# Log and GitHub annotation safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unsafe",
    [
        "https://user:supersecret@example.com",
        "https://example.com/?token=supersecret",
        "https://example.com/#supersecret",
    ],
)
def test_sensitive_urls_are_redacted_from_log_messages(unsafe: str) -> None:
    sanitized = tool.sanitize_for_log(f"cannot query {unsafe}: HTTP 404")

    assert "supersecret" not in sanitized
    assert sanitized == "cannot query https://example.com HTTP 404"


def test_network_exceptions_do_not_retain_a_sensitive_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = "https://user:supersecret@example.com/?token=supersecret#supersecret"

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise urllib.error.HTTPError(
            f"{index}/pypi/agnara/json", 403, "token=supersecret", Message(), io.BytesIO()
        )

    monkeypatch.setattr(tool.urllib.request, "urlopen", refuse)

    with pytest.raises(tool.Refusal) as caught:
        tool._index_json(index, "agnara")

    cause = caught.value.__cause__
    assert isinstance(cause, urllib.error.HTTPError)
    cause.close()
    message = tool.sanitize_for_log(caught.value)
    assert "supersecret" not in message
    assert message == "https://example.com returned HTTP 403 for agnara"


def test_main_sanitizes_external_exceptions_before_annotation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise tool.Refusal(
            "request to https://user:supersecret@example.com/?token=supersecret#supersecret failed"
        )

    monkeypatch.setattr(tool, "run", refuse)

    assert tool.main(["--version", VERSION]) == 2
    captured = capsys.readouterr()
    assert "supersecret" not in captured.out
    assert "supersecret" not in captured.err
    assert captured.out == (
        "::error::publication readiness could not be evaluated: "
        "request to https://example.com failed\n"
    )


def test_annotations_cannot_inject_new_workflow_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    injected = "failure\n::warning::token=supersecret\rnext\x00line%0A::notice::surprise"
    monkeypatch.setattr(tool, "run", lambda *args, **kwargs: (1, [injected], []))

    assert tool.main(["--version", VERSION]) == 1
    captured = capsys.readouterr()
    assert "supersecret" not in captured.out
    assert captured.err == ""
    assert captured.out.count("::error::") == 1
    assert "\n::warning::" not in captured.out
    assert "%0A" not in captured.out


def test_the_command_can_require_the_oidc_identity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, Any] = {}

    def record(*args: Any, **kwargs: Any) -> tuple[int, list[str], list[str]]:
        seen.update(kwargs)
        return 0, [], ["note"]

    monkeypatch.setattr(tool, "run", record)

    assert tool.main(["--version", VERSION, "--oidc-identity"]) == 0
    assert seen["oidc_identity"] is True
    assert "PUBLISH READY" in capsys.readouterr().out


@pytest.mark.parametrize(
    "unsafe",
    [
        "password=supersecret",
        "api_key:supersecret",
        "Authorization: Bearer supersecret",
        "github_pat_supersecret",
    ],
)
def test_recognizable_secret_formats_are_redacted(unsafe: str) -> None:
    assert "supersecret" not in tool.sanitize_for_log(f"request failed: {unsafe}")


# ---------------------------------------------------------------------------
# Publication order
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phases: three pending publishers at a time
# ---------------------------------------------------------------------------

BOOTSTRAP_1 = ("agnara-a2a", "agnara-cli", "agnara-events")
BOOTSTRAP_2 = ("agnara-http", "agnara-mcp", "agnara-telemetry")


def _complete(distribution: distributions.Distribution) -> dict[str, Any]:
    stem = distribution.artifact_stem
    return {
        "releases": {
            VERSION: [
                {"filename": f"{stem}-{VERSION}-py3-none-any.whl"},
                {"filename": f"{stem}-{VERSION}.tar.gz"},
            ]
        }
    }


def _index_after(*published: str) -> dict[str, Any]:
    """An index where exactly `published` are complete at VERSION; `agnara` always exists."""
    index: dict[str, Any] = {"agnara": {"releases": {}}}
    for distribution in MANIFEST.distributions:
        if distribution.name in published:
            index[distribution.name] = _complete(distribution)
    return index


def _kinds() -> dict[str, str]:
    return {name: ("active" if name == MANIFEST.core else "pending") for name in MANIFEST.names}


def test_the_phases_partition_the_reviewed_set_in_publication_order() -> None:
    """Every project is uploaded by exactly one phase, siblings first, kernel last."""
    phased = [name for phase in tool.PHASE_ORDER for name in tool.PHASES[phase]]

    assert sorted(phased) == sorted(MANIFEST.names)
    assert len(phased) == len(set(phased))
    assert tuple(phased) == MANIFEST.publication_order
    assert tool.PHASES[tool.FINAL_PHASE] == (MANIFEST.core,)
    assert tool.PHASE_ORDER[-1] == tool.FINAL_PHASE
    assert tool.projects_published_before("bootstrap-1") == ()
    assert tool.projects_published_before("bootstrap-2") == BOOTSTRAP_1
    assert tool.projects_published_before("final") == BOOTSTRAP_1 + BOOTSTRAP_2
    assert tool.projects_published_through("final") == MANIFEST.publication_order


def test_an_unknown_phase_is_refused() -> None:
    with pytest.raises(tool.Refusal, match="unknown release phase"):
        tool.phase_projects("bootstrap-3")


def _phase_record(verified: tuple[str, ...]) -> dict[str, Any]:
    """A record in which only `verified` were read back; the rest do not exist yet."""
    projects = [
        _project(name)
        if name in verified
        else _project(name, trusted_publisher="UNVERIFIED", verified_by=None, verified_on=None)
        for name in MANIFEST.names
    ]
    return {
        "status": "UNVERIFIED",
        "confirmed_by": None,
        "confirmed_on": None,
        "projects": projects,
    }


def test_bootstrap_1_requires_only_its_three_publishers(workspace: Path) -> None:
    """Before bootstrap-1 the other publishers cannot exist; readiness must not demand them."""
    _write_publication(workspace, _phase_record(BOOTSTRAP_1))

    assert _run(workspace, phase="bootstrap-1") == (0, [])


def test_bootstrap_1_still_refuses_an_unverified_publisher_of_its_own(workspace: Path) -> None:
    _write_publication(workspace, _phase_record(("agnara-a2a", "agnara-cli")))

    code, problems = _run(workspace, phase="bootstrap-1")

    assert code == 1
    assert problems == [
        "agnara-events: trusted_publisher is not VERIFIED; the owner must read back the pending "
        "publisher and record VERIFIED"
    ]


def test_bootstrap_2_requires_only_its_three_publishers(workspace: Path) -> None:
    _write_publication(workspace, _phase_record(BOOTSTRAP_2))

    assert _run(workspace, phase="bootstrap-2") == (0, [])


def test_the_final_phase_requires_only_the_kernel_publisher(workspace: Path) -> None:
    _write_publication(workspace, _phase_record((MANIFEST.core,)))

    assert _run(workspace, phase="final") == (0, [])


def test_without_a_phase_every_publisher_and_the_whole_record_are_required(
    workspace: Path,
) -> None:
    _write_publication(workspace, _phase_record(BOOTSTRAP_1))

    code, problems = _run(workspace)

    assert code == 1
    assert any("top-level status is not VERIFIED" in problem for problem in problems)
    assert sum("trusted_publisher is not VERIFIED" in problem for problem in problems) == 4


def test_a_phase_still_holds_every_project_to_its_canonical_name_and_environment(
    workspace: Path,
) -> None:
    record = _phase_record(BOOTSTRAP_1)
    for entry in record["projects"]:
        if entry["name"] == "agnara-http":
            entry["publisher_project"] = "agnara_http"
            entry["publisher_environment"] = "pypi"
    _write_publication(workspace, record)

    code, problems = _run(workspace, phase="bootstrap-1")

    assert code == 1
    assert any("agnara-http: Trusted Publisher project name" in problem for problem in problems)
    assert any("agnara-http: publisher_environment" in problem for problem in problems)


def test_an_upload_outside_its_phase_is_refused(workspace: Path) -> None:
    _write_publication(workspace, _phase_record(BOOTSTRAP_1))

    code, problems = _run(
        workspace,
        phase="bootstrap-1",
        oidc_identity=True,
        environ=ACTIONS_ENVIRON | {"GITHUB_JOB": "publish-http"},
        project="agnara-http",
        environment="pypi-http",
    )

    assert code == 1
    assert "agnara-http is not uploaded by phase bootstrap-1" in problems


def test_before_bootstrap_1_nothing_may_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_index(monkeypatch, _index_after())

    problems, notes = tool.check_index(
        MANIFEST,
        VERSION,
        index=tool.DEFAULT_INDEX,
        require_published=False,
        recorded_kinds=_kinds(),
        phase="bootstrap-1",
    )

    assert problems == []
    assert len(notes) == len(MANIFEST.names)


def test_bootstrap_2_requires_bootstrap_1_to_be_complete_on_the_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The previous phase is proven by the index, not by the record."""
    _stub_index(monkeypatch, _index_after("agnara-a2a", "agnara-cli"))

    problems, _ = tool.check_index(
        MANIFEST,
        VERSION,
        index=tool.DEFAULT_INDEX,
        require_published=False,
        recorded_kinds=_kinds(),
        phase="bootstrap-2",
    )

    assert problems == ["agnara-events: no project on https://pypi.org before this phase"]


def test_bootstrap_2_accepts_a_complete_bootstrap_1_without_re_reading_its_publishers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Their pending publishers were consumed; a record that still says
    `pending` for an existing project is history, not a stale readback."""
    _stub_index(monkeypatch, _index_after(*BOOTSTRAP_1))

    problems, notes = tool.check_index(
        MANIFEST,
        VERSION,
        index=tool.DEFAULT_INDEX,
        require_published=False,
        recorded_kinds=_kinds(),
        phase="bootstrap-2",
    )

    assert problems == []
    assert sum("wheel and sdist present" in note for note in notes) == 3


def test_a_phase_refuses_files_that_already_exist_for_its_own_or_a_later_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-publishing bootstrap-1 or publishing ahead of the phase is refused."""
    _stub_index(monkeypatch, _index_after(*BOOTSTRAP_1, "agnara-http", "agnara"))

    problems, _ = tool.check_index(
        MANIFEST,
        VERSION,
        index=tool.DEFAULT_INDEX,
        require_published=False,
        recorded_kinds=_kinds(),
        phase="bootstrap-2",
    )

    existing = [problem for problem in problems if "already has 2 file(s)" in problem]
    assert sorted(problem.split(" ", 1)[0] for problem in existing) == ["agnara", "agnara-http"]
    # And a project of this phase that already exists contradicts its `pending` readback.
    assert [problem for problem in problems if problem not in existing] == [
        "agnara-http: the record read back a publisher of kind 'pending', but the project is "
        "existing on https://pypi.org; re-verify it where PyPI actually holds it"
    ]


def test_verifying_bootstrap_1_requires_its_three_complete_and_nothing_else_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_index(monkeypatch, _index_after(*BOOTSTRAP_1))

    problems, notes = tool.check_index(
        MANIFEST, VERSION, index=tool.DEFAULT_INDEX, require_published=True, phase="bootstrap-1"
    )

    assert problems == []
    assert sum("wheel and sdist present" in note for note in notes) == 3
    assert sum("not published yet, as this phase intends" in note for note in notes) == 3
    assert any("agnara: project exists" in note for note in notes)


def test_verifying_bootstrap_1_fails_on_a_missing_sdist(monkeypatch: pytest.MonkeyPatch) -> None:
    index = _index_after(*BOOTSTRAP_1)
    index["agnara-cli"]["releases"][VERSION].pop()  # the sdist

    _stub_index(monkeypatch, index)

    problems, _ = tool.check_index(
        MANIFEST, VERSION, index=tool.DEFAULT_INDEX, require_published=True, phase="bootstrap-1"
    )

    assert problems == [
        f"agnara-cli {VERSION} is incomplete on https://pypi.org; missing "
        f"['agnara_cli-{VERSION}.tar.gz']"
    ]


def test_verifying_bootstrap_2_requires_all_six_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_index(monkeypatch, _index_after(*BOOTSTRAP_1, "agnara-http", "agnara-mcp"))

    problems, _ = tool.check_index(
        MANIFEST, VERSION, index=tool.DEFAULT_INDEX, require_published=True, phase="bootstrap-2"
    )

    assert problems == ["agnara-telemetry: no project on https://pypi.org after publication"]


def test_verifying_a_bootstrap_phase_refuses_a_kernel_published_ahead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The kernel last, even across phases: a tag would follow a premature kernel."""
    _stub_index(monkeypatch, _index_after(*BOOTSTRAP_1, *BOOTSTRAP_2, "agnara"))

    problems, _ = tool.check_index(
        MANIFEST, VERSION, index=tool.DEFAULT_INDEX, require_published=True, phase="bootstrap-2"
    )

    assert problems == [
        f"agnara {VERSION} already has 2 file(s) on https://pypi.org: "
        f"['agnara-{VERSION}-py3-none-any.whl', 'agnara-{VERSION}.tar.gz']. "
        "PyPI files are immutable; select the next version rather than republishing"
    ]


def test_verifying_the_final_phase_requires_all_seven(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_index(monkeypatch, _index_after(*MANIFEST.names))

    problems, notes = tool.check_index(
        MANIFEST, VERSION, index=tool.DEFAULT_INDEX, require_published=True, phase="final"
    )

    assert problems == []
    assert sum("wheel and sdist present" in note for note in notes) == len(MANIFEST.names)


def test_the_command_accepts_a_phase(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, Any] = {}

    def record(*args: Any, **kwargs: Any) -> tuple[int, list[str], list[str]]:
        seen.update(kwargs)
        return 0, [], ["note"]

    monkeypatch.setattr(tool, "run", record)

    assert tool.main(["--version", VERSION, "--phase", "bootstrap-2"]) == 0
    assert seen["phase"] == "bootstrap-2"
    assert "PUBLISH READY" in capsys.readouterr().out


def test_the_command_rejects_an_unknown_phase() -> None:
    with pytest.raises(SystemExit):
        tool.main(["--version", VERSION, "--phase", "bootstrap-3"])


def test_the_committed_record_is_ready_for_bootstrap_1_offline() -> None:
    """The owner read back the three bootstrap-1 publishers on 2026-09-09."""
    code, problems, notes = tool.run(
        WORKSPACE_ROOT,
        _repository_version(),
        dist_dir=None,
        tag=None,
        online=False,
        require_published=False,
        index=tool.DEFAULT_INDEX,
        phase="bootstrap-1",
    )

    assert (code, problems) == (0, [])
    assert any(
        "phase bootstrap-1: uploads agnara-a2a, agnara-cli, agnara-events" in n for n in notes
    )


def test_the_committed_record_is_ready_for_bootstrap_2_offline() -> None:
    """The owner read back the three bootstrap-2 publishers on 2026-09-09."""
    code, problems, notes = tool.run(
        WORKSPACE_ROOT,
        _repository_version(),
        dist_dir=None,
        tag=None,
        online=False,
        require_published=False,
        index=tool.DEFAULT_INDEX,
        phase="bootstrap-2",
    )

    assert (code, problems) == (0, [])
    assert any(
        "phase bootstrap-2: uploads agnara-http, agnara-mcp, agnara-telemetry" in n for n in notes
    )


def test_the_committed_record_does_not_yet_admit_the_final_phase() -> None:
    """The kernel's active publisher has not been read back for pypi-core yet."""
    for phase, expected in (("final", (MANIFEST.core,)),):
        code, problems, _ = tool.run(
            WORKSPACE_ROOT,
            _repository_version(),
            dist_dir=None,
            tag=None,
            online=False,
            require_published=False,
            index=tool.DEFAULT_INDEX,
            phase=phase,
        )
        assert code == 1, phase
        assert sorted(problem.split(":", 1)[0] for problem in problems) == sorted(expected), phase
        assert all("trusted_publisher is not VERIFIED" in problem for problem in problems), phase


def test_the_kernel_is_published_last() -> None:
    """A partial publication has to fail closed, and order is what decides it."""
    order = MANIFEST.publication_order

    assert order[-1] == MANIFEST.core
    assert set(order) == set(MANIFEST.names)
    assert len(order) == len(MANIFEST.names)
