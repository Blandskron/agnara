"""`scripts/check_publication_readiness.py` is the gate `0.1.0a4` did not have.

Its whole value is that it says no. These tests hold the refusals that matter:
an unconfirmed Trusted Publisher, a confirmation recorded for a different
version, a distribution left behind at another version, an adapter whose core
pin drifted, a missing release note, an incomplete artifact set, and a version
that already exists on the index.

A gate that can only pass is not a gate, so every case below constructs the
failure and asserts the script reports it.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

import distributions
from tests.architecture.boundaries import WORKSPACE_ROOT

VERSION = "9.9.9a1"


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
    _write_publication(root, {})
    return root


def _write_publication(root: Path, overrides: dict[str, Any]) -> None:
    document: dict[str, Any] = {
        "schema_version": 1,
        "target": VERSION,
        "publisher": dict(tool.REQUIRED_PUBLISHER),
        "projects": [
            {
                "name": name,
                "trusted_publisher": "VERIFIED",
                "verified_for_target": VERSION,
                "verified_by": "owner",
                "verified_on": "2026-09-08",
            }
            for name in MANIFEST.names
        ],
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
# The registry contract
# ---------------------------------------------------------------------------


def test_an_unverified_trusted_publisher_refuses_the_release(workspace: Path) -> None:
    """This single case is the whole `0.1.0a4` incident."""
    _write_publication(
        workspace,
        {
            "projects": [
                {"name": name, "trusted_publisher": "UNVERIFIED"} for name in MANIFEST.names
            ]
        },
    )

    code, problems = _run(workspace)

    assert code == 1
    assert len(problems) == len(MANIFEST.names)
    assert all("trusted_publisher is 'UNVERIFIED'" in problem for problem in problems)


def test_a_confirmation_recorded_for_another_version_does_not_carry_over(
    workspace: Path,
) -> None:
    """Publishers are checked per release, because they change between them."""
    _write_publication(
        workspace,
        {
            "projects": [
                {
                    "name": name,
                    "trusted_publisher": "VERIFIED",
                    "verified_for_target": "0.0.1a1",
                    "verified_by": "owner",
                    "verified_on": "2026-01-01",
                }
                for name in MANIFEST.names
            ]
        },
    )

    code, problems = _run(workspace)

    assert code == 1
    assert all("was recorded for '0.0.1a1'" in problem for problem in problems)


def test_a_confirmation_must_name_who_made_it(workspace: Path) -> None:
    _write_publication(
        workspace,
        {
            "projects": [
                {
                    "name": name,
                    "trusted_publisher": "VERIFIED",
                    "verified_for_target": VERSION,
                    "verified_by": None,
                    "verified_on": None,
                }
                for name in MANIFEST.names
            ]
        },
    )

    code, problems = _run(workspace)

    assert code == 1
    assert all("who verified it and when" in problem for problem in problems)


def test_a_missing_project_confirmation_is_not_silently_skipped(workspace: Path) -> None:
    document = json.loads(
        (workspace / "docs" / "releases" / "publication.json").read_text(encoding="utf-8")
    )
    document["projects"] = [
        entry for entry in document["projects"] if entry["name"] != "agnara-mcp"
    ]
    (workspace / "docs" / "releases" / "publication.json").write_text(
        json.dumps(document), encoding="utf-8"
    )

    code, problems = _run(workspace)

    assert code == 1
    assert any("no publisher confirmation recorded for ['agnara-mcp']" in p for p in problems)


def test_a_different_publisher_tuple_is_refused(workspace: Path) -> None:
    """A tuple that differs in any field is a different identity to PyPI."""
    publisher = dict(tool.REQUIRED_PUBLISHER) | {"environment": "release"}
    _write_publication(workspace, {"publisher": publisher})

    code, problems = _run(workspace)

    assert code == 1
    assert any("publisher tuple must be" in problem for problem in problems)


def test_the_record_must_name_the_version_being_published(workspace: Path) -> None:
    _write_publication(workspace, {"target": "0.0.1a1"})

    code, problems = _run(workspace)

    assert code == 1
    assert any("records target '0.0.1a1'" in problem for problem in problems)


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
# Publication order
# ---------------------------------------------------------------------------


def test_the_kernel_is_published_last() -> None:
    """A partial publication has to fail closed, and order is what decides it."""
    order = MANIFEST.publication_order

    assert order[-1] == MANIFEST.core
    assert set(order) == set(MANIFEST.names)
    assert len(order) == len(MANIFEST.names)
