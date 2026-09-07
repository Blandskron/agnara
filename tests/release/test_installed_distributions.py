"""Building a distribution and being able to use it are different claims.

`scripts/check_installed_distributions.py` is the gate that makes the second
one checkable. These tests hold the properties that make it worth running: it
discovers what to check instead of being told, it fails when a distribution is
absent, misplaced, incomplete or inconsistent, and it never passes by finding
nothing to look at.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.architecture.boundaries import DISTRIBUTIONS, WORKSPACE_ROOT


def _load_checker() -> Any:
    """Load the script by path; `scripts/` is tooling, not an importable package."""
    location = WORKSPACE_ROOT / "scripts" / "check_installed_distributions.py"
    spec = importlib.util.spec_from_file_location("agnara_installed_distributions", location)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves annotations through `sys.modules[cls.__module__]`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


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

    code, lines = checker.run(tmp_path, require_installed=False)

    assert code == 1
    assert any("no distributions found" in line for line in lines)


def test_a_missing_packages_directory_is_reported(tmp_path: Path) -> None:
    code, lines = checker.run(tmp_path, require_installed=False)

    assert code == 1
    assert any("no packages directory" in line for line in lines)


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


def test_unsynchronized_versions_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0021 keeps every pre-one version identical across the seven packages."""
    found, _ = checker.discover(WORKSPACE_ROOT)
    real = checker.importlib.metadata.version

    def drifted(name: str) -> str:
        return "9.9.9" if name == "agnara-cli" else real(name)

    monkeypatch.setattr(checker.importlib.metadata, "version", drifted)

    problems = checker.check_metadata(found)

    assert any("versions are not synchronized" in problem for problem in problems)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def test_the_workspace_passes_without_the_install_requirement() -> None:
    """The development environment is a valid subject for everything but origin."""
    code, lines = checker.run(WORKSPACE_ROOT, require_installed=False)

    assert code == 0, lines
    assert any("checked 7 installed distributions" in line for line in lines)


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
    code = checker.main(["--workspace", str(tmp_path)])
    captured = capsys.readouterr()

    assert code == 1
    assert "::error::" in captured.out
