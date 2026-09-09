"""Building a distribution and being able to use it are different claims.

`scripts/check_distributions.py` is the gate that makes the second
one checkable. These tests hold the properties that make it worth running: it
discovers what to check instead of being told, it fails when a distribution is
absent, misplaced, incomplete or inconsistent, and it never passes by finding
nothing to look at.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest

from tests.architecture.boundaries import DISTRIBUTIONS, WORKSPACE_ROOT


def _load_checker() -> Any:
    """Load the script by path; `scripts/` is tooling, not an importable package."""
    location = WORKSPACE_ROOT / "scripts" / "check_distributions.py"
    spec = importlib.util.spec_from_file_location("agnara_distributions", location)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves annotations through `sys.modules[cls.__module__]`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()
WORKSPACE_VERSION = tomllib.loads(
    (WORKSPACE_ROOT / "packages" / "agnara" / "pyproject.toml").read_text(encoding="utf-8")
)["project"]["version"]


def _workspace(tmp_path: Path, packages: dict[str, list[str]]) -> Path:
    """A minimal workspace: distribution name -> the packages under its src/."""
    for distribution, modules in packages.items():
        for module in modules:
            source = tmp_path / "packages" / distribution / "src" / module
            source.mkdir(parents=True)
            (source / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Discovery -- the gate must not need a list to stay complete
# ---------------------------------------------------------------------------


def test_discovery_finds_every_documented_distribution() -> None:
    """The set the gate checks must equal the set the repository documents."""
    found, problems = checker.discover(WORKSPACE_ROOT)

    assert not problems
    assert {distribution.name for distribution in found} == set(DISTRIBUTIONS)


def test_discovery_maps_each_distribution_to_its_import_name() -> None:
    found, _ = checker.discover(WORKSPACE_ROOT)

    assert {d.name: d.import_name for d in found} == DISTRIBUTIONS


def test_an_ambiguous_package_is_reported_rather_than_guessed(tmp_path: Path) -> None:
    """Two importable packages under one src/ would make the gate check the wrong one."""
    workspace = _workspace(tmp_path, {"agnara-x": ["agnara_x", "agnara_y"]})

    found, problems = checker.discover(workspace)

    assert not found
    assert any("expected exactly one importable package" in problem for problem in problems)


def test_a_package_with_no_importable_source_is_reported(tmp_path: Path) -> None:
    (tmp_path / "packages" / "agnara-empty" / "src").mkdir(parents=True)

    found, problems = checker.discover(tmp_path)

    assert not found
    assert any("agnara-empty" in problem for problem in problems)


def test_an_empty_workspace_never_passes_by_checking_nothing(tmp_path: Path) -> None:
    """The failure that would make this gate meaningless."""
    (tmp_path / "packages").mkdir()

    report = checker.run(tmp_path, require_installed=False)

    assert report.code == 1
    assert any("no distributions found" in problem for problem in report.problems)


def test_a_missing_packages_directory_is_reported(tmp_path: Path) -> None:
    report = checker.run(tmp_path, require_installed=False)

    assert report.code == 1
    assert any("no packages directory" in problem for problem in report.problems)


# ---------------------------------------------------------------------------
# Import origin
# ---------------------------------------------------------------------------


def test_a_distribution_that_does_not_import_fails() -> None:
    absent = checker.Distribution(name="agnara-absent", import_name="agnara_absent_module")

    problems = checker.check_import(absent, workspace=WORKSPACE_ROOT, require_installed=False)

    assert any("cannot import" in problem for problem in problems)


def test_importing_from_the_checkout_fails_when_an_install_is_required() -> None:
    """The development environment imports from `packages/*/src`, so this must fail."""
    core = checker.Distribution(name="agnara", import_name="agnara")

    problems = checker.check_import(core, workspace=WORKSPACE_ROOT, require_installed=True)

    assert any("imported from the checkout" in problem for problem in problems)
    assert any("not an installed location" in problem for problem in problems)


def test_the_same_import_passes_when_an_install_is_not_required() -> None:
    """`--require-installed` is the only thing that rejects a source-tree import."""
    core = checker.Distribution(name="agnara", import_name="agnara")

    assert checker.check_import(core, workspace=WORKSPACE_ROOT, require_installed=False) == []


# ---------------------------------------------------------------------------
# Package data -- what an import check cannot see
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("distribution", sorted(DISTRIBUTIONS))
def test_every_distribution_ships_a_typing_marker(distribution: str) -> None:
    """PEP 561: without `py.typed` the shipped annotations are ignored."""
    found = checker.Distribution(name=distribution, import_name=DISTRIBUTIONS[distribution])

    assert "py.typed" in checker.data_files(WORKSPACE_ROOT, found)


def test_the_vendored_documentation_assets_are_discovered() -> None:
    """ADR 0040 serves these from the installed package, so they must be checked."""
    http = checker.Distribution(name="agnara-http", import_name="agnara_http")

    vendored = [name for name in checker.data_files(WORKSPACE_ROOT, http) if "_vendor/" in name]

    assert vendored
    assert any(name.endswith(".js") for name in vendored)


def test_package_data_is_checked_against_the_installed_package(tmp_path: Path) -> None:
    """A data file present in the source but absent once installed is a defect."""
    workspace = _workspace(tmp_path, {"agnara-fake": ["agnara"]})
    (workspace / "packages" / "agnara-fake" / "src" / "agnara" / "absent.json").write_text(
        "{}", encoding="utf-8"
    )
    fake = checker.Distribution(name="agnara-fake", import_name="agnara")

    problems = checker.check_package_data(fake, workspace=workspace)

    assert any("not reachable from the installed package" in problem for problem in problems)


def test_a_distribution_with_no_data_files_reports_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, {"agnara-fake": ["agnara"]})
    fake = checker.Distribution(name="agnara-fake", import_name="agnara")

    assert checker.check_package_data(fake, workspace=workspace) == []


# ---------------------------------------------------------------------------
# Installed metadata
# ---------------------------------------------------------------------------


def test_every_adapter_declares_its_dependency_on_the_core() -> None:
    found, _ = checker.discover(WORKSPACE_ROOT)

    assert checker.check_metadata(found) == []


def test_a_distribution_without_installed_metadata_fails() -> None:
    absent = checker.Distribution(name="agnara-not-installed", import_name="agnara")

    problems = checker.check_metadata([absent])

    assert any("no installed distribution metadata" in problem for problem in problems)


def test_an_adapter_that_lost_its_core_dependency_fails() -> None:
    """`agnara-cli` requires `agnara`; naming a different core proves the check runs."""
    found, _ = checker.discover(WORKSPACE_ROOT)
    adapters = [d for d in found if d.name == "agnara-cli"]

    problems = checker.check_metadata(adapters, core="agnara-something-else")

    assert any("does not declare a dependency" in problem for problem in problems)


@pytest.mark.parametrize(
    "requirement",
    ["agnara", "agnara>=0.1.0a4.dev0", "agnara==0.1.0a3", "agnara[extra]==0.1.0a4.dev0"],
)
def test_an_adapter_without_the_exact_matching_core_pin_fails(
    monkeypatch: pytest.MonkeyPatch, requirement: str
) -> None:
    adapter = checker.Distribution(name="agnara-http", import_name="agnara_http")
    monkeypatch.setattr(checker.importlib.metadata, "version", lambda name: "0.1.0a4.dev0")
    monkeypatch.setattr(checker.importlib.metadata, "requires", lambda name: [requirement])

    problems = checker.check_metadata([adapter])

    assert any("must require agnara==0.1.0a4.dev0 exactly" in problem for problem in problems)


def test_normalized_exact_core_pin_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = checker.Distribution(name="agnara-http", import_name="agnara_http")
    monkeypatch.setattr(checker.importlib.metadata, "version", lambda name: "0.1.0a4.dev0")
    monkeypatch.setattr(
        checker.importlib.metadata,
        "requires",
        lambda name: ["Agnara == 0.1.0a4.dev0"],
    )

    assert checker.check_metadata([adapter]) == []


def test_unsynchronized_versions_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0021 keeps every pre-one version identical across the seven packages."""
    found, _ = checker.discover(WORKSPACE_ROOT)
    real = checker.importlib.metadata.version

    def drifted(name: str) -> str:
        return "9.9.9" if name == "agnara-cli" else real(name)

    monkeypatch.setattr(checker.importlib.metadata, "version", drifted)

    problems = checker.check_metadata(found)

    assert any("versions are not synchronized" in problem for problem in problems)


def test_an_installed_version_that_does_not_match_the_tag_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = checker.Distribution(name="agnara", import_name="agnara")
    monkeypatch.setattr(checker.importlib.metadata, "version", lambda name: "0.1.0a4")

    problems = checker.check_metadata([core], expected_version="0.1.0a5")

    assert any("do not match expected 0.1.0a5" in problem for problem in problems)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def test_the_workspace_passes_without_the_install_requirement() -> None:
    """The development environment is a valid subject for everything but origin."""
    report = checker.run(WORKSPACE_ROOT, require_installed=False)

    assert report.code == 0, report.problems
    assert report.problems == ()
    assert "checked 7 installed distributions" in report.summary


def test_success_says_what_it_inspected(capsys: pytest.CaptureFixture[str]) -> None:
    """A gate that prints nothing cannot be told apart from one that never ran."""
    code = checker.main(["--workspace", str(WORKSPACE_ROOT)])
    captured = capsys.readouterr()

    assert code == 0
    assert "checked 7 installed distributions" in captured.out
    assert "::error::" not in captured.out


def test_failures_are_reported_as_workflow_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The log line is a constant: not even the failing path or a count leaks."""
    code = checker.main(["--workspace", str(tmp_path)])
    captured = capsys.readouterr()

    assert code == 1
    assert captured.out == "::error::distribution validation failed\n"
    assert captured.err == ""
    assert str(tmp_path) not in captured.out


def test_failure_output_does_not_log_untrusted_diagnostics(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Whatever ``run`` reports about the artifact stays out of stdout/stderr.

    The report is deliberately poisoned in every field, including the summary,
    so the test also holds if ``main`` ever starts trusting the wrong one.
    """
    marker = "pypi-" + "A" * 60
    poisoned = checker.Report(
        1,
        f"summary mentions {marker}",
        (
            f"agnara: wheel contains a recognized credential signature in ['{marker}']",
            "agnara: wheel retains the local build path in ['/home/runner/work/agnara']",
            "agnara: sensitive filename shipped: agnara/.env",
            "password=hunter2",
        ),
    )
    monkeypatch.setattr(checker, "run", lambda *_args, **_kwargs: poisoned)

    code = checker.main(["--workspace", str(WORKSPACE_ROOT)])
    captured = capsys.readouterr()

    assert code == 1
    assert captured.out == "::error::distribution validation failed\n"
    assert captured.err == ""
    for fragment in (marker, "hunter2", "/home/runner", ".env", "summary mentions", "4"):
        assert fragment not in captured.out
        assert fragment not in captured.err


# ---------------------------------------------------------------------------
# Built artifacts
# ---------------------------------------------------------------------------


def _built(tmp_path: Path, names: list[str]) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    for name in names:
        (dist / name).write_bytes(b"")
    return dist


def _artifacts_for(distributions: list[Any]) -> list[str]:
    names = []
    for distribution in distributions:
        stem = distribution.name.replace("-", "_")
        names += [
            f"{stem}-{WORKSPACE_VERSION}-py3-none-any.whl",
            f"{stem}-{WORKSPACE_VERSION}.tar.gz",
        ]
    return names


def test_a_complete_build_passes(tmp_path: Path) -> None:
    found, _ = checker.discover(WORKSPACE_ROOT)
    dist = _built(tmp_path, _artifacts_for(found))

    assert checker.check_built_artifacts(found, dist) == []


def test_uv_s_own_gitignore_is_not_an_artifact(tmp_path: Path) -> None:
    """`uv build` writes a .gitignore into the output directory it creates.

    Treating it as a stray artifact failed the packaging job on a clean
    checkout, where `dist/` does not exist until the build makes it.
    """
    found, _ = checker.discover(WORKSPACE_ROOT)
    dist = _built(tmp_path, _artifacts_for(found))
    (dist / ".gitignore").write_text("*", encoding="utf-8")

    assert checker.check_built_artifacts(found, dist) == []


def test_a_missing_wheel_fails(tmp_path: Path) -> None:
    found, _ = checker.discover(WORKSPACE_ROOT)
    names = _artifacts_for(found)
    missing = f"agnara_http-{WORKSPACE_VERSION}-py3-none-any.whl"
    dist = _built(tmp_path, [n for n in names if n != missing])

    problems = checker.check_built_artifacts(found, dist)

    assert any("agnara-http: expected 1 wheel, found []" in problem for problem in problems)


def test_a_missing_sdist_fails(tmp_path: Path) -> None:
    found, _ = checker.discover(WORKSPACE_ROOT)
    names = _artifacts_for(found)
    missing = f"agnara_mcp-{WORKSPACE_VERSION}.tar.gz"
    dist = _built(tmp_path, [n for n in names if n != missing])

    problems = checker.check_built_artifacts(found, dist)

    assert any("agnara-mcp: expected 1 sdist, found []" in problem for problem in problems)


def test_a_stale_artifact_from_another_release_fails(tmp_path: Path) -> None:
    """Two versions of one distribution would let a glob validate the wrong one."""
    found, _ = checker.discover(WORKSPACE_ROOT)
    dist = _built(tmp_path, [*_artifacts_for(found), "agnara-0.1.0a2-py3-none-any.whl"])

    problems = checker.check_built_artifacts(found, dist)

    assert any("expected 1 wheel" in problem for problem in problems)


def test_an_artifact_from_an_unknown_distribution_fails(tmp_path: Path) -> None:
    found, _ = checker.discover(WORKSPACE_ROOT)
    dist = _built(tmp_path, [*_artifacts_for(found), "somethingelse-1.0-py3-none-any.whl"])

    problems = checker.check_built_artifacts(found, dist)

    assert any("unexpected artifacts" in problem for problem in problems)


def test_a_missing_build_directory_is_reported(tmp_path: Path) -> None:
    found, _ = checker.discover(WORKSPACE_ROOT)

    problems = checker.check_built_artifacts(found, tmp_path / "absent")

    assert any("no build output directory" in problem for problem in problems)


def test_the_artifact_mode_never_imports_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It runs before installation, so an import failure would say nothing."""
    found, _ = checker.discover(WORKSPACE_ROOT)
    dist = _built(tmp_path, _artifacts_for(found))
    monkeypatch.setattr(checker, "check_artifact_contents", lambda *args, **kwargs: [])

    report = checker.run(WORKSPACE_ROOT, dist_dir=dist)

    assert report.code == 0
    assert report.problems == ()
    assert "built 7 distributions" in report.summary


def test_the_release_set_is_explicit_and_matches_the_architecture() -> None:
    """The checker's own reader of the manifest must agree with everything else.

    `check_distributions.py` parses `docs/distributions.json` itself rather
    than importing `scripts/distributions.py`, because its installed-artifact
    mode runs under `python -I`, which implies `-P` and removes the script's
    own directory from `sys.path`. Two readers of one file is acceptable; two
    readers that disagree is not.
    """
    assert checker.shipped_distributions(WORKSPACE_ROOT) == DISTRIBUTIONS


def test_an_accidental_workspace_distribution_is_not_publishable() -> None:
    found, _ = checker.discover(WORKSPACE_ROOT)
    found.append(checker.Distribution("agnara-accidental", "agnara_accidental"))

    problems = checker.check_release_set(found, DISTRIBUTIONS)

    assert any("unexpected=['agnara-accidental']" in problem for problem in problems)


def test_a_direct_or_git_dependency_is_rejected() -> None:
    for requirement in (
        "agnara @ file:///tmp/agnara.whl",
        "agnara @ git+https://example.invalid/agnara.git@develop",
    ):
        with pytest.raises(ValueError, match="unsupported direct/editable dependency"):
            checker._canonical_requirement(requirement)


def test_archive_paths_reject_development_files_secrets_and_traversal() -> None:
    problems = checker._safe_archive_names(
        ["pkg/tests/test_hidden.py", "pkg/.env", "../outside"], "agnara"
    )

    assert any("development/cache" in problem for problem in problems)
    assert any("sensitive filename" in problem for problem in problems)
    assert any("unsafe archive member" in problem for problem in problems)


def test_local_build_paths_are_detected_in_artifact_content() -> None:
    native = f"generated at {WORKSPACE_ROOT}".encode()
    uri = f"source = {WORKSPACE_ROOT.as_uri()}".encode()

    assert checker._contains_workspace_path(native, WORKSPACE_ROOT)
    assert checker._contains_workspace_path(uri, WORKSPACE_ROOT)
    assert not checker._contains_workspace_path(b"portable package content", WORKSPACE_ROOT)


@pytest.mark.parametrize(
    "payload",
    [
        b"-----BEGIN PRIVATE KEY-----",
        b"pypi-" + b"A" * 60,
        b"ghp_" + b"A" * 40,
        b"AKIA" + b"A" * 16,
    ],
)
def test_recognized_secret_signatures_are_detected(payload: bytes) -> None:
    assert checker._contains_secret_signature(payload)


def test_ordinary_package_text_is_not_a_secret_signature() -> None:
    assert not checker._contains_secret_signature(b"no credentials are stored here")


def test_invalid_archives_fail_instead_of_crashing(tmp_path: Path) -> None:
    found, _ = checker.discover(WORKSPACE_ROOT)
    dist = _built(tmp_path, _artifacts_for(found))

    problems = checker.check_artifact_contents(found, workspace=WORKSPACE_ROOT, dist_dir=dist)

    assert any("invalid wheel archive" in problem for problem in problems)
    assert any("invalid sdist archive" in problem for problem in problems)


def _metadata(distribution: str, *, body: str | None = None) -> bytes:
    project = tomllib.loads(
        (WORKSPACE_ROOT / "packages" / distribution / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    lines = [
        "Metadata-Version: 2.5",
        f"Name: {project['name']}",
        f"Version: {project['version']}",
        "Author-email: Agnara Maintainers <maintainers@agnara.dev>",
        "License: Apache-2.0",
        "License-File: LICENSE",
        f"Requires-Python: {project['requires-python']}",
        "Description-Content-Type: text/markdown",
    ]
    lines.extend(f"Project-URL: {name}, {url}" for name, url in project["urls"].items())
    lines.extend(f"Classifier: {classifier}" for classifier in project["classifiers"])
    lines.extend(f"Requires-Dist: {requirement}" for requirement in project["dependencies"])
    if body is None:
        body = (WORKSPACE_ROOT / "packages" / distribution / "README.md").read_text(
            encoding="utf-8"
        )
    return ("\n".join(lines) + "\n\n" + body).encode()


@pytest.mark.parametrize("distribution", sorted(DISTRIBUTIONS))
def test_complete_wheel_metadata_and_entry_points_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, distribution: str
) -> None:
    found = checker.Distribution(distribution, DISTRIBUTIONS[distribution])
    project = tomllib.loads(
        (WORKSPACE_ROOT / "packages" / distribution / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    wheel = tmp_path / "candidate.whl"
    dist_info = f"{distribution.replace('-', '_')}-{project['version']}.dist-info"
    monkeypatch.setattr(checker, "data_files", lambda *args: ["py.typed"])
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"{found.import_name}/__init__.py", "")
        archive.writestr(f"{found.import_name}/py.typed", "")
        archive.writestr(f"{dist_info}/METADATA", _metadata(distribution))
        archive.writestr(f"{dist_info}/licenses/LICENSE", (WORKSPACE_ROOT / "LICENSE").read_bytes())
        scripts = project.get("scripts", {})
        if scripts:
            rendered = "[console_scripts]\n" + "\n".join(
                f"{name} = {target}" for name, target in scripts.items()
            )
            archive.writestr(f"{dist_info}/entry_points.txt", rendered)

    assert checker._check_wheel(found, workspace=WORKSPACE_ROOT, wheel=wheel) == []


def test_a_wheel_without_a_readme_description_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = checker.Distribution("agnara", "agnara")
    version = WORKSPACE_VERSION
    wheel = tmp_path / "candidate.whl"
    monkeypatch.setattr(checker, "data_files", lambda *args: ["py.typed"])
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("agnara/__init__.py", "")
        archive.writestr("agnara/py.typed", "")
        archive.writestr(f"agnara-{version}.dist-info/METADATA", _metadata("agnara", body=""))
        archive.writestr(
            f"agnara-{version}.dist-info/licenses/LICENSE",
            (WORKSPACE_ROOT / "LICENSE").read_bytes(),
        )

    problems = checker._check_wheel(found, workspace=WORKSPACE_ROOT, wheel=wheel)

    assert any("contains no README description" in problem for problem in problems)


def _add_tar_text(archive: tarfile.TarFile, name: str, text: str = "") -> None:
    payload = text.encode()
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    archive.addfile(member, io.BytesIO(payload))


def test_sdist_requires_license_readme_project_and_package(tmp_path: Path) -> None:
    found = checker.Distribution("agnara", "agnara")
    root = f"agnara-{WORKSPACE_VERSION}"
    sdist = tmp_path / "candidate.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        source_files = {
            "LICENSE": WORKSPACE_ROOT / "LICENSE",
            "README.md": WORKSPACE_ROOT / "packages" / "agnara" / "README.md",
            "pyproject.toml": WORKSPACE_ROOT / "packages" / "agnara" / "pyproject.toml",
            "src/agnara/__init__.py": (
                WORKSPACE_ROOT / "packages" / "agnara" / "src" / "agnara" / "__init__.py"
            ),
        }
        for relative, source in source_files.items():
            _add_tar_text(archive, f"{root}/{relative}", source.read_text(encoding="utf-8"))

    assert checker._check_sdist(found, workspace=WORKSPACE_ROOT, sdist=sdist) == []

    missing = tmp_path / "missing.tar.gz"
    with tarfile.open(missing, "w:gz") as archive:
        _add_tar_text(archive, f"{root}/LICENSE")

    problems = checker._check_sdist(found, workspace=WORKSPACE_ROOT, sdist=missing)
    assert any("README.md" in problem for problem in problems)
