"""Smoke tests for the workspace layout defined by EPIC 0.

These assert that every package boundary named in ``ARCHITECTURE.md``
section 3 actually exists, is importable on the baseline interpreter and
declares the metadata the tooling depends on. Dependency-direction rules
are enforced separately by the architecture tests (E0.7).
"""

import importlib
import sys
import tomllib
from importlib.metadata import distribution

import pytest

from tests.architecture.boundaries import (
    DISTRIBUTIONS,
    PACKAGES_DIR,
    WORKSPACE_ROOT,
)


def read_package_pyproject(dist_name: str) -> dict:
    path = PACKAGES_DIR / dist_name / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_baseline_interpreter_is_python_314_or_newer() -> None:
    """ADR 0001: Python 3.14 is the minimum supported version."""
    assert sys.version_info >= (3, 14)


def test_workspace_root_is_virtual() -> None:
    """The root is a workspace root, not a distributable package."""
    root = tomllib.loads((WORKSPACE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "project" not in root
    assert root["tool"]["uv"]["workspace"]["members"] == ["packages/*"]


def test_workspace_contains_exactly_the_documented_packages() -> None:
    """ARCHITECTURE.md section 3 names seven packages and no others."""
    found = {
        path.name
        for path in PACKAGES_DIR.iterdir()
        if path.is_dir() and not path.name.startswith((".", "_"))
    }
    assert found == set(DISTRIBUTIONS)


@pytest.mark.parametrize("dist_name", sorted(DISTRIBUTIONS))
def test_package_is_installed_in_the_workspace_environment(dist_name: str) -> None:
    assert distribution(dist_name).metadata["Name"] == dist_name


@pytest.mark.parametrize(("dist_name", "import_name"), sorted(DISTRIBUTIONS.items()))
def test_import_name_matches_adr_0017(dist_name: str, import_name: str) -> None:
    module = importlib.import_module(import_name)
    assert module.__doc__, f"{import_name} must document its responsibility"


@pytest.mark.parametrize("dist_name", sorted(DISTRIBUTIONS))
def test_package_requires_python_314(dist_name: str) -> None:
    """E0.3: every package pins the same baseline."""
    assert read_package_pyproject(dist_name)["project"]["requires-python"] == ">=3.14"


@pytest.mark.parametrize("dist_name", sorted(DISTRIBUTIONS))
def test_package_ships_py_typed(dist_name: str) -> None:
    """PEP 561: the packages are typed, so the marker must be present."""
    import_name = DISTRIBUTIONS[dist_name]
    marker = PACKAGES_DIR / dist_name / "src" / import_name / "py.typed"
    assert marker.is_file()


def test_core_exposes_its_version() -> None:
    import agnara

    assert agnara.__version__ == distribution("agnara-core").version
