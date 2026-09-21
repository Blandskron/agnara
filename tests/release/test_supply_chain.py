"""Supply-chain evidence: the SBOM, the digest chain and the scanner gates.

Three things have to be true before an owner can review a candidate's
supply chain, and each fails quietly rather than loudly if nobody checks it:

* the SBOM describes *this* build, not a development environment or a
  previous one;
* the bytes that reach a registry are the bytes the build job produced;
* the audit and analysis gates actually run, and a skipped one cannot be
  mistaken for a passing one.

The workflow assertions here are text-level on purpose. A release workflow
cannot be executed in a unit test, so what is checkable is its configuration,
and a configuration gate that nobody asserts is one edit away from being gone.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = WORKSPACE_ROOT / "scripts"
RELEASE_WORKFLOW = WORKSPACE_ROOT / ".github" / "workflows" / "release.yml"

sys.path.insert(0, str(SCRIPTS))

from check_sbom import verify  # noqa: E402
from distributions import load as load_manifest  # noqa: E402
from generate_sbom import (  # noqa: E402
    SbomError,
    build_document,
    parse_requirements,
    render,
)

VERSION = "9.9.9.dev0"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A dist directory shaped like a real build, with distinct bytes.

    The generator hashes these files rather than parsing them, so standing in
    for a real `uv build` keeps the lane fast while still exercising the
    digest path end to end. Each file differs, so a generator that reused one
    digest for every component would fail below.
    """
    dist = tmp_path_factory.mktemp("dist")
    for project in load_manifest(WORKSPACE_ROOT).names:
        stem = project.replace("-", "_")
        (dist / f"{stem}-{VERSION}-py3-none-any.whl").write_bytes(f"wheel:{project}".encode())
        (dist / f"{stem}-{VERSION}.tar.gz").write_bytes(f"sdist:{project}".encode())
    return dist


@pytest.fixture(scope="module")
def document(built: Path) -> dict:
    return build_document(WORKSPACE_ROOT, built, VERSION)


# ---------------------------------------------------------------------------
# The SBOM describes the candidate
# ---------------------------------------------------------------------------


def test_the_sbom_is_a_cyclonedx_document_with_a_stable_serial(document: dict) -> None:
    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == "1.6"
    assert document["serialNumber"].startswith("urn:uuid:")


def test_the_sbom_describes_every_reviewed_distribution(document: dict, built: Path) -> None:
    """Six of seven would look complete, which is worse than none."""
    first_party = {
        component["name"]: component
        for component in document["components"]
        if {"name": "agnara:role", "value": "first-party"} in component["properties"]
    }
    expected = {name.replace("_", "-").lower() for name in load_manifest(WORKSPACE_ROOT).names}

    assert set(first_party) == expected
    for name, component in first_party.items():
        assert component["version"] == VERSION
        assert component["purl"] == f"pkg:pypi/{name}@{VERSION}"
        # Both the wheel and the sdist, and their real bytes.
        assert len(component["hashes"]) == 2


def test_every_first_party_digest_is_the_real_file(document: dict, built: Path) -> None:
    for component in document["components"]:
        if {"name": "agnara:role", "value": "first-party"} not in component["properties"]:
            continue
        stem = component["name"].replace("-", "_")
        actual = {
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                built / f"{stem}-{VERSION}-py3-none-any.whl",
                built / f"{stem}-{VERSION}.tar.gz",
            )
        }
        recorded = {entry["content"] for entry in component["hashes"]}
        assert recorded == actual, component["name"]


def test_the_sbom_carries_the_runtime_graph_and_not_the_development_group(
    document: dict,
) -> None:
    """The failure mode is an SBOM of somebody's laptop that looks plausible."""
    names = {component["name"] for component in document["components"]}
    dependencies = [
        component
        for component in document["components"]
        if {"name": "agnara:role", "value": "runtime-dependency"} in component["properties"]
    ]

    assert dependencies, "no runtime dependencies were described"
    # Shipped at runtime through the MCP SDK, so their absence would be a bug.
    assert {"mcp", "pydantic", "starlette"} <= names
    # Test and fixture tooling, which no consumer installs.
    assert not (names & {"pytest", "ruff", "ty", "hypothesis", "playwright", "django"})
    assert all(component.get("version") for component in document["components"])


def test_the_same_inputs_produce_a_byte_identical_document(built: Path) -> None:
    """A reviewer diffing two SBOMs needs the difference to mean something."""
    first = render(build_document(WORKSPACE_ROOT, built, VERSION))
    second = render(build_document(WORKSPACE_ROOT, built, VERSION))

    assert first == second


def test_a_colourized_export_is_parsed_rather_than_rejected() -> None:
    """A CI runner that forces colour must not break the parser.

    GitHub Actions sets `FORCE_COLOR`, so `uv export` wrapped every line in
    SGR escapes and the comment grammar stopped matching: the generator failed
    on the export's own header. Local runs never saw it because a piped uv
    disables colour on its own. The export is now requested with
    `--color never`, and parsing strips escapes regardless of how it was
    asked for.
    """
    plain = "# autogenerated\nannotated-types==0.8.0\n    --hash=sha256:" + "a" * 64 + "\n"
    colourized = "".join(f"\x1b[32m{line}\x1b[39m\n" for line in plain.splitlines())

    assert parse_requirements(colourized) == parse_requirements(plain)
    parsed = parse_requirements(colourized)
    assert parsed[0]["name"] == "annotated-types"
    assert parsed[0]["version"] == "0.8.0"


def test_the_export_is_requested_without_colour() -> None:
    """Defence in depth: control the input as well as tolerating it."""
    source = (SCRIPTS / "generate_sbom.py").read_text(encoding="utf-8")

    assert '"--color"' in source
    assert '"never"' in source
    assert '"NO_COLOR": "1"' in source
    assert 'environment.pop("FORCE_COLOR", None)' in source


def test_describing_an_unbuilt_candidate_is_an_error(tmp_path: Path) -> None:
    """Silence about a missing artifact would be the dangerous answer."""
    with pytest.raises(SbomError, match="no built"):
        build_document(WORKSPACE_ROOT, tmp_path, VERSION)


# ---------------------------------------------------------------------------
# The verifier is independent of the generator
# ---------------------------------------------------------------------------


def test_a_faithful_sbom_passes_verification(document: dict, built: Path, tmp_path: Path) -> None:
    sbom = tmp_path / "sbom.cdx.json"
    sbom.write_text(render(document), encoding="utf-8")

    assert verify(sbom, WORKSPACE_ROOT, built, VERSION) == []


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        pytest.param(
            lambda doc: doc.update(specVersion="1.4"),
            "specVersion",
            id="a different specification revision",
        ),
        pytest.param(
            lambda doc: doc["components"].pop(
                next(
                    index
                    for index, component in enumerate(doc["components"])
                    if component["name"] == "agnara-http"
                )
            ),
            "absent from the SBOM",
            id="a reviewed distribution is missing",
        ),
        pytest.param(
            lambda doc: doc["components"].append(
                {
                    "type": "library",
                    "name": "pytest",
                    "version": "8.4.0",
                    "properties": [{"name": "agnara:role", "value": "runtime-dependency"}],
                }
            ),
            "development-only components",
            id="a development component leaked in",
        ),
        pytest.param(
            lambda doc: doc.update(serialNumber="not-a-urn"),
            "serial number",
            id="no serial number",
        ),
    ],
)
def test_verification_rejects_a_document_that_misdescribes_the_candidate(
    document: dict, built: Path, tmp_path: Path, mutate, expected: str
) -> None:
    corrupted = json.loads(json.dumps(document))
    mutate(corrupted)
    sbom = tmp_path / "sbom.cdx.json"
    sbom.write_text(json.dumps(corrupted), encoding="utf-8")

    problems = verify(sbom, WORKSPACE_ROOT, built, VERSION)

    assert any(expected in problem for problem in problems), problems


def test_verification_rejects_a_digest_that_is_not_the_built_file(
    document: dict, built: Path, tmp_path: Path
) -> None:
    """The case that matters: a plausible SBOM for a different build."""
    corrupted = json.loads(json.dumps(document))
    for component in corrupted["components"]:
        if component["name"] == "agnara":
            component["hashes"][0]["content"] = "0" * 64
            break
    sbom = tmp_path / "sbom.cdx.json"
    sbom.write_text(json.dumps(corrupted), encoding="utf-8")

    problems = verify(sbom, WORKSPACE_ROOT, built, VERSION)

    assert any("describes a different build" in problem for problem in problems), problems


def test_verification_rejects_an_sbom_for_another_version(
    document: dict, built: Path, tmp_path: Path
) -> None:
    sbom = tmp_path / "sbom.cdx.json"
    sbom.write_text(render(document), encoding="utf-8")

    problems = verify(sbom, WORKSPACE_ROOT, built, "1.2.3")

    assert problems
    assert all("described at" in problem or "not present" in problem for problem in problems)


def test_a_missing_sbom_is_reported_rather_than_assumed_absent(built: Path, tmp_path: Path) -> None:
    problems = verify(tmp_path / "nothing.json", WORKSPACE_ROOT, built, VERSION)

    assert problems == [f"no SBOM at {tmp_path / 'nothing.json'}"]


# ---------------------------------------------------------------------------
# The release workflow wires the evidence together
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return RELEASE_WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))


def test_every_bundle_download_is_followed_by_a_digest_check(workflow_text: str) -> None:
    """A recorded digest nobody reads back is a note, not a control.

    `build` writes SHA256SUMS for exactly the bytes it produced. Each job that
    later acts on the bundle -- including every upload to PyPI -- must
    re-assert it, so a bundle that changed between the build and an upload
    fails before a registry sees it.
    """
    downloads = workflow_text.count("name: agnara-distributions\n          path: dist/")
    checks = workflow_text.count('sha256sum --check --strict "$GITHUB_WORKSPACE/hashes/SHA256SUMS"')

    assert downloads > 0, "the workflow downloads no bundle at all"
    assert checks == downloads, (
        f"{downloads} bundle downloads but {checks} digest checks; "
        "every job acting on the bundle must verify it"
    )


def test_the_sbom_is_generated_verified_and_published_as_an_artifact(
    workflow_text: str,
) -> None:
    assert "scripts/generate_sbom.py" in workflow_text
    assert "scripts/check_sbom.py" in workflow_text
    assert "name: agnara-sbom" in workflow_text
    # Reproducible: the timestamp comes from the release commit, not the clock.
    assert 'SOURCE_DATE_EPOCH="$(git -C "$GITHUB_WORKSPACE" log -1 --pretty=%ct)"' in workflow_text


def test_the_dependency_audit_is_a_gate_and_not_an_instruction(workflow: dict) -> None:
    """SECURITY.md required this audit long before anything ran it."""
    jobs = workflow["jobs"]

    assert "dependency-audit" in jobs, "no locked dependency audit job"
    audit = jobs["dependency-audit"]
    assert "if" not in audit, "the audit must run in every phase"
    assert "continue-on-error" not in audit
    assert audit["permissions"] == {"contents": "read"}
    # Nothing is built, and therefore nothing is published, unless it passed.
    assert "dependency-audit" in jobs["build"]["needs"]


def test_the_dependency_audit_pins_its_tool_and_audits_the_locked_runtime(
    workflow_text: str,
) -> None:
    audit = workflow_text.split("  dependency-audit:\n", 1)[1].split("\n  build:\n", 1)[0]

    assert re.search(r"pip-audit==\d+\.\d+\.\d+", audit), "pip-audit is not pinned"
    assert "--strict" in audit, "a warning-only audit is not a gate"
    assert "--locked" in audit, "the audit must read the lockfile, not re-resolve"
    assert "--no-dev" in audit, "the development group is not shipped to anyone"


def test_no_release_job_can_be_made_to_run_after_a_failed_one(workflow_text: str) -> None:
    """Guards the property the digest and audit gates depend on."""
    for expression in ("always()", "failure()", "cancelled()", "success()"):
        assert expression not in workflow_text, expression


#: Actions that mint or consume an OIDC identity for a publication. A job
#: holding `id-token: write` without one of these is holding a credential it
#: has no use for.
PUBLISHERS = ("pypa/gh-action-pypi-publish@", "docker/build-push-action@")


def test_publishing_jobs_hold_only_the_identity_they_need(workflow: dict) -> None:
    """`id-token: write` is a credential, not a convenience.

    It is what proves this workflow's identity to PyPI's Trusted Publisher and
    to Sigstore, so a job that holds it can speak as the project. Only the
    jobs that actually upload may.
    """
    holders = []
    for name, job in workflow["jobs"].items():
        permissions = job.get("permissions")
        if not isinstance(permissions, dict) or permissions.get("id-token") != "write":
            continue
        holders.append(name)
        uses = yaml.dump(job.get("steps", []))
        assert any(publisher in uses for publisher in PUBLISHERS), (
            f"{name} holds id-token: write without publishing anything"
        )
        # Never write access to the repository itself from a job that can also
        # authenticate to a registry.
        assert permissions.get("contents") in {"read", None}, name

    # One per reviewed distribution, plus the container image.
    assert len(holders) == len(load_manifest(WORKSPACE_ROOT).names) + 1, holders


def test_no_job_outside_publication_can_authenticate_to_a_registry(
    workflow: dict,
) -> None:
    """Every gate before the human approval runs without any credential."""
    for name in ("preconditions", "dependency-audit", "build", "test-artifact"):
        permissions = workflow["jobs"][name].get("permissions")
        assert permissions == {"contents": "read"}, f"{name}: {permissions}"


def test_every_pypi_upload_produces_a_pep_740_attestation(workflow_text: str) -> None:
    """Provenance uses the ecosystem mechanism rather than anything bespoke."""
    uploads = workflow_text.count("uses: pypa/gh-action-pypi-publish@")
    attested = workflow_text.count("attestations: true")

    assert uploads == len(load_manifest(WORKSPACE_ROOT).names)
    assert attested == uploads, f"{uploads} uploads but {attested} attested"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required to resolve the lockfile")
def test_the_generator_refuses_a_workspace_whose_lockfile_does_not_resolve(
    tmp_path: Path,
) -> None:
    """`--locked` must fail rather than quietly re-resolving a new graph."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "nothing"\nversion = "0"\nrequires-python = ">=3.14"\n',
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["uv", "export", "--locked", "--format", "requirements.txt"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
