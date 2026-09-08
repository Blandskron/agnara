"""I1: the exposure model's boundaries, as rules rather than intentions.

The unified exposure model is the layer most likely to acquire a protocol
dependency, because it is the layer both protocol adapters talk to. These
tests are the executable form of RFC 0006 invariants 1, 5 and 6 and of
ARCHITECTURE.md section 3.

They must fail when:

- the exposure package imports an adapter, an SDK or a non-standard library;
- the exposure package imports `agnara.introspection`, which would make the
  dependency between availability and publication bidirectional and
  reintroduce the import cycle this layering exists to avoid;
- a compiled exposure can reach a runtime object;
- an adapter reaches into a private core module instead of the public one.
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pytest

from agnara.capability import CapabilityId
from agnara.exposure import CompiledExposure, ExposureId, SurfaceId
from tests.architecture.boundaries import (
    CORE_DISTRIBUTION,
    WORKSPACE_ROOT,
    _file_imports,
    is_standard_library,
    package_source_root,
)

EXPOSURE_ROOT = package_source_root(CORE_DISTRIBUTION) / "exposure"

#: Adapters that contribute to the model today. A third one joining must not
#: require a change here or in the kernel, which is the point of the model.
CONTRIBUTORS = ("agnara-http", "agnara-mcp")


def exposure_imports() -> list[tuple[str, str]]:
    """Every module the exposure package imports, with where it does it."""
    return [
        (imp.module, imp.where())
        for path in sorted(EXPOSURE_ROOT.rglob("*.py"))
        for imp in _file_imports(path)
    ]


def test_the_exposure_package_exists_where_the_manifest_says() -> None:
    assert EXPOSURE_ROOT.is_dir()
    assert (EXPOSURE_ROOT / "__init__.py").is_file()


def test_the_exposure_package_imports_only_stdlib_and_the_kernel() -> None:
    offenders = [
        (module, where)
        for module, where in exposure_imports()
        if module != "agnara" and not is_standard_library(module)
    ]
    assert not offenders, "agnara.exposure may import only the standard library and agnara:\n" + (
        "\n".join(f"  {where} imports {module!r}" for module, where in offenders)
    )


def dotted_imports() -> list[tuple[str, str]]:
    """Full dotted module names the exposure package imports, with location.

    `_file_imports` reports only the top-level module, which cannot tell
    `agnara.capability` from `agnara.introspection`. Parsing the AST here
    keeps docstrings and comments out of the answer, which a text search
    would not.
    """
    found: list[tuple[str, str]] = []
    for path in sorted(EXPOSURE_ROOT.rglob("*.py")):
        where = path.relative_to(WORKSPACE_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend((alias.name, f"{where}:{node.lineno}") for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.append((node.module, f"{where}:{node.lineno}"))
    return found


def test_the_exposure_package_does_not_import_introspection() -> None:
    """Availability must not depend on publication.

    `agnara.introspection` derives descriptors from the exposure registry, so
    the edge points one way. Adding the reverse edge would be a cycle, and the
    reason `CompiledExposure` carries canonical JSON detail rather than an
    `ExposureDescriptor` is precisely to keep it absent.
    """
    offenders = [
        (module, where)
        for module, where in dotted_imports()
        if module == "agnara.introspection" or module.startswith("agnara.introspection.")
    ]
    assert not offenders, (
        "agnara.exposure must not import agnara.introspection; the dependency "
        f"points the other way: {offenders}"
    )


@pytest.mark.parametrize(
    "first",
    ["agnara.exposure", "agnara.introspection", "agnara"],
)
def test_the_exposure_package_imports_cleanly_in_any_order(first: str) -> None:
    """A cycle shows up as an ImportError only for one of the orders.

    Run each order in a fresh interpreter, because the test process has
    already imported everything and would hide the problem.
    """
    script = f"import {first}; import agnara.exposure, agnara.introspection"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_the_exposure_package_names_no_adapter() -> None:
    offenders = [
        path.relative_to(WORKSPACE_ROOT).as_posix()
        for path in sorted(EXPOSURE_ROOT.rglob("*.py"))
        for name in ("agnara_http", "agnara_mcp", "agnara_a2a", "agnara_events")
        if name in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"agnara.exposure must not name an adapter package: {offenders}"


def test_a_compiled_exposure_cannot_reach_a_runtime_object() -> None:
    """RFC 0006 invariant 5: a neutral record alone cannot dispatch."""
    exposure = CompiledExposure.of(
        SurfaceId("http", "public"),
        "POST /refunds",
        CapabilityId("billing", "refund"),
        {"method": "POST"},
    )

    reachable = {
        name: getattr(exposure, name)
        for name in dir(exposure)
        if not name.startswith("__") and not callable(getattr(exposure, name, None))
    }
    for value in reachable.values():
        assert isinstance(value, str | SurfaceId | CapabilityId | ExposureId), value


@pytest.mark.parametrize("distribution", CONTRIBUTORS)
def test_a_contributing_adapter_uses_the_public_exposure_surface(distribution: str) -> None:
    """An adapter imports `agnara.exposure`, never a private module inside it."""
    root = package_source_root(distribution)
    private = [
        path.relative_to(WORKSPACE_ROOT).as_posix()
        for path in sorted(root.rglob("*.py"))
        for fragment in ("agnara.exposure.identity", "agnara.exposure.compiled")
        if fragment in path.read_text(encoding="utf-8")
    ]
    assert not private, f"{distribution} must import from agnara.exposure: {private}"


@pytest.mark.parametrize("distribution", CONTRIBUTORS)
def test_a_contributing_adapter_does_import_the_model(distribution: str) -> None:
    """The point of the model is that both adapters actually go through it."""
    root = package_source_root(distribution)
    users = [
        path.relative_to(WORKSPACE_ROOT).as_posix()
        for path in sorted(root.rglob("*.py"))
        if "from agnara.exposure import" in path.read_text(encoding="utf-8")
    ]
    assert users, f"{distribution} contributes no exposure records"
