"""Tests for the architecture-rule detectors themselves.

An architecture test that cannot fail is worse than no test, because it
reports safety it never checked. These cases feed known-bad input to the
detectors in ``boundaries`` and assert that each violation is reported.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tests.architecture import boundaries
from tests.architecture.boundaries import (
    FORBIDDEN_IN_CORE,
    _file_imports,
    _requirement_name,
    find_cycle,
    is_standard_library,
)


def write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "module.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------


def test_detects_a_plain_import(tmp_path: Path) -> None:
    path = write(tmp_path, "import fastapi\n")
    assert [imp.module for imp in _file_imports(path)] == ["fastapi"]


def test_detects_a_dotted_import_by_its_top_level_name(tmp_path: Path) -> None:
    path = write(tmp_path, "import opentelemetry.trace.status\n")
    assert [imp.module for imp in _file_imports(path)] == ["opentelemetry"]


def test_detects_a_from_import(tmp_path: Path) -> None:
    path = write(tmp_path, "from pydantic.fields import Field\n")
    assert [imp.module for imp in _file_imports(path)] == ["pydantic"]


def test_detects_an_import_hidden_inside_a_function(tmp_path: Path) -> None:
    """A lazy import is still a boundary crossing."""
    path = write(
        tmp_path,
        """
        def build():
            import starlette

            return starlette
        """,
    )
    assert [imp.module for imp in _file_imports(path)] == ["starlette"]


def test_detects_an_import_inside_a_type_checking_block(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        """
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from msgspec import Struct
        """,
    )
    assert {imp.module for imp in _file_imports(path)} == {"typing", "msgspec"}


def test_ignores_relative_imports(tmp_path: Path) -> None:
    """Relative imports are intra-package and never cross a boundary."""
    path = write(tmp_path, "from . import registry\nfrom .plan import Plan\n")
    assert list(_file_imports(path)) == []


def test_records_the_location_of_a_violation(tmp_path: Path) -> None:
    path = write(tmp_path, "\n\nimport litestar\n")
    (imp,) = _file_imports(path)
    assert imp.lineno == 3


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_standard_library_is_recognised() -> None:
    assert is_standard_library("asyncio")
    assert is_standard_library("dataclasses")
    assert not is_standard_library("fastapi")


@pytest.mark.parametrize(
    "forbidden", ["fastapi", "starlette", "pydantic", "msgspec", "mcp", "opentelemetry"]
)
def test_forbidden_dependencies_are_not_standard_library(forbidden: str) -> None:
    """The denylist must not shadow a standard-library name."""
    assert forbidden in FORBIDDEN_IN_CORE
    assert not is_standard_library(forbidden)


@pytest.mark.parametrize(
    ("requirement", "expected"),
    [
        ("agnara-core", "agnara-core"),
        ("agnara-core>=0.1", "agnara-core"),
        ("agnara-core[extra]", "agnara-core"),
        ("agnara-core ; python_version >= '3.14'", "agnara-core"),
        ("agnara-core @ file:///tmp/x", "agnara-core"),
        ("agnara-core==0.0.0", "agnara-core"),
    ],
)
def test_requirement_names_are_extracted(requirement: str, expected: str) -> None:
    assert _requirement_name(requirement) == expected


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


def test_acyclic_graph_reports_no_cycle() -> None:
    graph = {"a": {"b"}, "b": {"c"}, "c": set()}
    assert find_cycle(graph) is None


def test_detects_a_direct_cycle() -> None:
    cycle = find_cycle({"a": {"b"}, "b": {"a"}})
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"a", "b"}


def test_detects_an_indirect_cycle() -> None:
    cycle = find_cycle({"a": {"b"}, "b": {"c"}, "c": {"a"}})
    assert cycle is not None
    assert set(cycle) == {"a", "b", "c"}


def test_detects_a_self_cycle() -> None:
    assert find_cycle({"a": {"a"}}) == ["a", "a"]


def test_diamond_is_not_a_cycle() -> None:
    graph = {"a": {"b", "c"}, "b": {"d"}, "c": {"d"}, "d": set()}
    assert find_cycle(graph) is None


# ---------------------------------------------------------------------------
# End-to-end: a violation planted in a real package is caught
# ---------------------------------------------------------------------------


def test_a_forbidden_core_import_would_be_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plant a forbidden import in a fake core package and confirm it fails.

    This exercises the same path the real rule uses, so the rule cannot
    silently stop inspecting sources.
    """
    fake_core = tmp_path / "packages" / "agnara-core" / "src" / "agnara"
    fake_core.mkdir(parents=True)
    (fake_core / "__init__.py").write_text("import pydantic\n", encoding="utf-8")

    monkeypatch.setattr(boundaries, "PACKAGES_DIR", tmp_path / "packages")
    monkeypatch.setattr(boundaries, "WORKSPACE_ROOT", tmp_path)

    offenders = [
        imp
        for imp in boundaries.external_imports_of("agnara-core")
        if not boundaries.is_standard_library(imp.module)
    ]
    assert [imp.module for imp in offenders] == ["pydantic"]


def test_a_sibling_adapter_import_would_be_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_http = tmp_path / "packages" / "agnara-http" / "src" / "agnara_http"
    fake_http.mkdir(parents=True)
    (fake_http / "__init__.py").write_text("import agnara_mcp\n", encoding="utf-8")

    monkeypatch.setattr(boundaries, "PACKAGES_DIR", tmp_path / "packages")
    monkeypatch.setattr(boundaries, "WORKSPACE_ROOT", tmp_path)

    modules = [imp.module for imp in boundaries.external_imports_of("agnara-http")]
    assert "agnara_mcp" in modules
