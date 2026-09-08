"""Everything that names a distribution must name the same seven.

`docs/distributions.json` is the single source of truth (ADR 0079). It replaced
five independent copies of the same list, of which exactly one pair was ever
compared. A copy that nothing checks is not a safeguard; it is a second answer
waiting to disagree with the first.

Some copies cannot be removed. GitHub Actions cannot loop a `uses:` step, so
the seven upload steps are written out; `uv` needs its workspace sources
declared; `ty` needs its import roots. Those are held to the manifest here
instead, so a change to the reviewed set fails the test suite until every
derived list follows.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

import distributions
from tests.architecture.boundaries import WORKSPACE_ROOT


def _load_script(name: str, module_name: str) -> Any:
    """Load a release script by path; `scripts/` is tooling, not a package."""
    spec = importlib.util.spec_from_file_location(module_name, WORKSPACE_ROOT / "scripts" / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_script("check_distributions.py", "agnara_publication_set_distributions")
readiness = _load_script("check_release_readiness.py", "agnara_publication_set_readiness")

MANIFEST_PATH = WORKSPACE_ROOT / "docs" / "distributions.json"
ROOT_PYPROJECT = WORKSPACE_ROOT / "pyproject.toml"
RELEASE_WORKFLOW = WORKSPACE_ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = WORKSPACE_ROOT / ".github" / "workflows" / "ci.yml"

MANIFEST = distributions.load(WORKSPACE_ROOT)


def _root_metadata() -> dict[str, Any]:
    return tomllib.loads(ROOT_PYPROJECT.read_text(encoding="utf-8"))


def _workflow(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The manifest itself
# ---------------------------------------------------------------------------


def test_the_manifest_describes_the_packages_that_exist() -> None:
    on_disk = sorted(
        child.name for child in (WORKSPACE_ROOT / "packages").iterdir() if child.is_dir()
    )

    assert on_disk == sorted(MANIFEST.names)


@pytest.mark.parametrize("distribution", MANIFEST.distributions, ids=lambda d: d.name)
def test_each_declared_distribution_matches_its_project_metadata(
    distribution: distributions.Distribution,
) -> None:
    path = WORKSPACE_ROOT / "packages" / distribution.name / "pyproject.toml"
    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    wheel = tomllib.loads(path.read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"][
        "wheel"
    ]

    assert project["name"] == distribution.name
    assert wheel["packages"] == [f"src/{distribution.import_name}"]
    assert sorted(project.get("scripts", {})) == sorted(distribution.console_scripts)


def test_declared_third_party_requirements_are_the_ones_the_packages_declare() -> None:
    """A clean-room install resolves these before the index is closed.

    If an adapter gains a third-party dependency and the manifest does not, the
    release workflow closes the index without it and the install fails at the
    worst moment. This is the check that fails first instead.
    """
    for distribution in MANIFEST.distributions:
        path = WORKSPACE_ROOT / "packages" / distribution.name / "pyproject.toml"
        declared = tomllib.loads(path.read_text(encoding="utf-8"))["project"]["dependencies"]
        third_party = [
            requirement
            for requirement in declared
            if not requirement.startswith(tuple(MANIFEST.names))
        ]

        assert third_party == list(distribution.third_party_requirements), distribution.name


def test_exactly_one_kernel_and_it_depends_on_nothing_first_party() -> None:
    core = MANIFEST.get(MANIFEST.core)

    assert core.role == "kernel"
    assert [d.role for d in MANIFEST.distributions].count("kernel") == 1
    path = WORKSPACE_ROOT / "packages" / core.name / "pyproject.toml"
    assert tomllib.loads(path.read_text(encoding="utf-8"))["project"]["dependencies"] == []


def test_artifact_stems_normalize_the_dash_rather_than_renaming_the_project() -> None:
    """`agnara_a2a-…` is PEP 427/625 normalization of `agnara-a2a`, not a typo.

    The `0.1.0a4` failure was reported against a file whose name contained an
    underscore, which makes it tempting to "fix" the project name. The
    canonical name is the dash form; the filename normalization is correct and
    is what PyPI expects.
    """
    assert MANIFEST.get("agnara-a2a").artifact_stem == "agnara_a2a"
    for distribution in MANIFEST.distributions:
        assert "-" not in distribution.artifact_stem
        assert distribution.artifact_stem == distribution.name.replace("-", "_")


# ---------------------------------------------------------------------------
# Every consumer
# ---------------------------------------------------------------------------


def test_the_distribution_checker_reads_the_same_set() -> None:
    assert checker.shipped_distributions(WORKSPACE_ROOT) == MANIFEST.mapping


def test_the_readiness_checker_reads_the_same_set() -> None:
    assert MANIFEST.mapping == readiness.DISTRIBUTIONS


def test_the_workspace_declares_every_distribution_as_a_uv_source() -> None:
    sources = _root_metadata()["tool"]["uv"]["sources"]

    assert sorted(sources) == sorted(MANIFEST.names)
    assert all(source == {"workspace": True} for source in sources.values())


def test_the_dev_group_installs_every_distribution() -> None:
    dev = _root_metadata()["dependency-groups"]["dev"]
    first_party = [requirement for requirement in dev if requirement in set(MANIFEST.names)]

    assert sorted(first_party) == sorted(MANIFEST.names)


def test_the_type_checker_sees_every_import_root() -> None:
    roots = _root_metadata()["tool"]["ty"]["environment"]["root"]
    package_roots = {
        root for root in roots if root.startswith("packages/") and root.endswith("/src")
    }

    assert package_roots == {f"packages/{name}/src" for name in MANIFEST.names}


# ---------------------------------------------------------------------------
# The release workflow
# ---------------------------------------------------------------------------


def test_every_distribution_is_published_by_its_own_step_in_publication_order() -> None:
    """Siblings first, the kernel last, one step each.

    `0.1.0a4` handed all fourteen files to one invocation, so the order was
    `twine`'s filename sort rather than a decision, and the kernel went first.
    That published a version of `agnara` whose adapters did not exist.
    """
    steps = _workflow(RELEASE_WORKFLOW)["jobs"]["publish"]["steps"]
    published = [
        step["with"]["packages-dir"].removeprefix("staged/")
        for step in steps
        if str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish")
    ]

    assert tuple(published) == MANIFEST.publication_order
    assert published[-1] == MANIFEST.core


def test_no_publish_step_suppresses_an_existing_file() -> None:
    """`skip-existing` would make a rerun over a partial publication look green."""
    steps = _workflow(RELEASE_WORKFLOW)["jobs"]["publish"]["steps"]

    for step in steps:
        if str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish"):
            options = step["with"]
            assert "skip-existing" not in options
            assert options["verify-metadata"] is True
            assert options["attestations"] is True


def test_the_github_release_cannot_exist_without_verified_publication() -> None:
    """The `0.1.0a4` shape -- publish, verify and announce as steps of one job --
    let a failed upload cancel the other two silently. They are jobs now, and
    the dependency is what makes the ordering a guarantee rather than a hope.
    """
    jobs = _workflow(RELEASE_WORKFLOW)["jobs"]

    assert "publish-preflight" in jobs["publish"]["needs"]
    assert "publish" in jobs["verify-published"]["needs"]
    assert "verify-published" in jobs["github-release"]["needs"]


def test_only_the_publishing_job_holds_an_oidc_token_and_it_cannot_write_contents() -> None:
    jobs = _workflow(RELEASE_WORKFLOW)["jobs"]
    holders = [
        name
        for name, job in jobs.items()
        if isinstance(job.get("permissions"), dict)
        and job["permissions"].get("id-token") == "write"
    ]

    assert holders == ["publish"]
    assert jobs["publish"]["permissions"]["contents"] == "read"
    assert jobs["publish"]["environment"]["name"] == "pypi"
    writers = [
        name
        for name, job in jobs.items()
        if isinstance(job.get("permissions"), dict)
        and job["permissions"].get("contents") == "write"
    ]
    assert writers == ["github-release"]


def test_publication_requires_a_pushed_tag() -> None:
    """ADR 0073 decision 6: a manual dispatch may validate and never publish."""
    jobs = _workflow(RELEASE_WORKFLOW)["jobs"]

    for name in ("publish-preflight", "publish"):
        condition = jobs[name]["if"]
        assert "github.event_name == 'push'" in condition
        assert "refs/tags/v" in condition


# ---------------------------------------------------------------------------
# Supply chain
# ---------------------------------------------------------------------------

_SHA_PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40} # \S+$")


@pytest.mark.parametrize("workflow", [RELEASE_WORKFLOW, CI_WORKFLOW], ids=lambda p: p.name)
def test_every_third_party_action_is_pinned_to_a_commit_with_its_version_named(
    workflow: Path,
) -> None:
    """A movable tag on a job that can obtain `id-token: write` is a decision.

    The trailing comment is required as well as the SHA: a bare forty
    characters tells a reviewer nothing about what they are approving, and
    Dependabot rewrites the comment together with the pin.
    """
    # The trailing comment is part of the pin, and YAML discards comments, so
    # this reads the lines rather than the parsed document.
    references = [
        line.strip().removeprefix("- ").removeprefix("uses: ")
        for line in workflow.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(("- uses:", "uses:"))
    ]
    third_party = [reference for reference in references if not reference.startswith("./")]

    assert third_party, "no third-party actions found; this test would prove nothing"
    for reference in third_party:
        assert _SHA_PINNED.match(reference), f"{workflow.name}: {reference!r} is not SHA-pinned"


# ---------------------------------------------------------------------------
# The manifest refuses to be wrong quietly
# ---------------------------------------------------------------------------


def _write(path: Path, document: dict[str, Any]) -> Path:
    (path / "docs").mkdir(parents=True, exist_ok=True)
    (path / "docs" / "distributions.json").write_text(json.dumps(document), encoding="utf-8")
    return path


def _document(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": 1,
        "core": "agnara",
        "distributions": [
            {"name": "agnara", "import_name": "agnara", "role": "kernel"},
            {"name": "agnara-http", "import_name": "agnara_http", "role": "adapter"},
        ],
    }
    document.update(overrides)
    return document


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"schema_version": 2}, "schema_version"),
        ({"core": "not-a-distribution"}, "not one of the declared"),
        (
            {
                "distributions": [
                    {"name": "agnara-http", "import_name": "agnara_http", "role": "adapter"},
                    {"name": "agnara", "import_name": "agnara", "role": "kernel"},
                ]
            },
            "canonical name order",
        ),
        (
            {
                "distributions": [
                    {"name": "agnara", "import_name": "agnara", "role": "kernel"},
                    {"name": "agnara-http", "import_name": "agnara_http", "role": "kernel"},
                ]
            },
            "role 'kernel'",
        ),
        (
            {
                "distributions": [
                    {"name": "agnara", "import_name": "agnara", "role": "wrong"},
                ]
            },
            "'role' must be one of",
        ),
    ],
)
def test_a_malformed_manifest_is_refused(
    tmp_path: Path, overrides: dict[str, Any], expected: str
) -> None:
    _write(tmp_path, _document(**overrides))

    with pytest.raises(distributions.ManifestError, match=re.escape(expected)):
        distributions.load(tmp_path)


def test_a_missing_manifest_is_refused_rather_than_defaulted(tmp_path: Path) -> None:
    with pytest.raises(distributions.ManifestError, match="cannot read"):
        distributions.load(tmp_path)
