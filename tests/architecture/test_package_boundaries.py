"""E0.7 — automated architecture rules.

These tests are the executable form of the dependency rules in
``ARCHITECTURE.md`` sections 3 and 4, ``PRINCIPLES.md`` P2/P3/P13,
``AGENTS.md`` "Core invariants" and ADR 0003.

They must fail when:

- ``agnara`` imports a forbidden dependency;
- protocol-neutral policy tests import a transport or protocol SDK;
- an adapter imports a sibling adapter;
- a package cycle appears;
- a new ``agnara`` runtime dependency is introduced.
"""

from __future__ import annotations

import ast

import pytest

from tests.architecture.boundaries import (
    ADAPTER_DISTRIBUTIONS,
    CORE_DISTRIBUTION,
    CORE_IMPORT_NAME,
    DISTRIBUTIONS,
    FORBIDDEN_IN_CORE,
    WORKSPACE_ROOT,
    _file_imports,
    _requirement_name,
    declared_dependencies,
    declared_workspace_dependencies,
    dependency_graph,
    external_imports_of,
    find_cycle,
    import_graph,
    is_standard_library,
    source_files,
)

# ---------------------------------------------------------------------------
# Rule 1 — the core imports nothing but the standard library
# ---------------------------------------------------------------------------


def test_core_imports_only_the_standard_library() -> None:
    """PRINCIPLES.md P3: ``agnara`` prefers the standard library.

    This is the general form of the forbidden-dependency rule: anything that
    is neither the standard library nor ``agnara`` itself is a new core
    dependency and needs an ADR before it may appear here.
    """
    offenders = [
        imp for imp in external_imports_of(CORE_DISTRIBUTION) if not is_standard_library(imp.module)
    ]
    assert not offenders, "agnara may import only the standard library:\n" + "\n".join(
        f"  {imp.where()} imports {imp.module!r}" for imp in offenders
    )


def test_core_does_not_import_forbidden_dependencies() -> None:
    """AGENTS.md: the core is never coupled to a protocol, server or SDK."""
    offenders = [
        imp for imp in external_imports_of(CORE_DISTRIBUTION) if imp.module in FORBIDDEN_IN_CORE
    ]
    assert not offenders, (
        "agnara imports a dependency forbidden by AGENTS.md and ADR 0003:\n"
        + "\n".join(f"  {imp.where()} imports {imp.module!r}" for imp in offenders)
    )


def test_core_declares_no_runtime_dependencies() -> None:
    """A new core runtime dependency must not slip in through packaging."""
    declared = declared_dependencies(CORE_DISTRIBUTION)
    assert declared == [], (
        "agnara must declare no runtime dependencies; CONTRIBUTING.md "
        f"requires an explicit justification for each one. Found: {declared}"
    )


def test_core_does_not_import_any_adapter() -> None:
    """ADR 0003: dependencies point inward. Core never imports an adapter."""
    adapter_import_names = {DISTRIBUTIONS[dist] for dist in ADAPTER_DISTRIBUTIONS}
    offenders = [
        imp for imp in external_imports_of(CORE_DISTRIBUTION) if imp.module in adapter_import_names
    ]
    assert not offenders, "agnara must not import an adapter:\n" + "\n".join(
        f"  {imp.where()} imports {imp.module!r}" for imp in offenders
    )


def test_policy_tests_are_independent_of_transports() -> None:
    """BACKLOG E5.7: policy behavior is tested without transport coupling."""
    policy_test_paths = sorted((WORKSPACE_ROOT / "tests" / "unit" / "policy").rglob("*.py"))
    policy_test_paths.append(
        WORKSPACE_ROOT / "tests" / "unit" / "execution" / "test_policy_runtime.py"
    )
    adapter_import_names = {DISTRIBUTIONS[distribution] for distribution in ADAPTER_DISTRIBUTIONS}
    disallowed = FORBIDDEN_IN_CORE | adapter_import_names
    offenders = [
        imported
        for path in policy_test_paths
        for imported in _file_imports(path)
        if imported.module in disallowed
    ]

    assert not offenders, "policy tests must remain transport-neutral:\n" + "\n".join(
        f"  {imported.where()} imports {imported.module!r}" for imported in offenders
    )


# ---------------------------------------------------------------------------
# Rule 2 — adapters do not import sibling adapters
# ---------------------------------------------------------------------------


def test_telemetry_declares_api_without_sdk_or_exporter_dependencies() -> None:
    declared = {
        _requirement_name(requirement) for requirement in declared_dependencies("agnara-telemetry")
    }
    assert declared == {"agnara", "opentelemetry-api"}


def test_telemetry_imports_no_sdk_or_exporter_implementation() -> None:
    forbidden = ("opentelemetry.sdk", "opentelemetry.exporter")
    offenders = []
    for path in source_files("agnara-telemetry"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
            else:
                continue
            for module in modules:
                if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden):
                    offenders.append(f"{path.name}:{node.lineno}: {module}")
    assert not offenders, "telemetry must use only the OpenTelemetry API: " + ", ".join(offenders)


@pytest.mark.parametrize("dist_name", ADAPTER_DISTRIBUTIONS)
def test_adapter_does_not_import_a_sibling_adapter(dist_name: str) -> None:
    """ARCHITECTURE.md section 4: cross-adapter imports are forbidden.

    Behaviour needed by two adapters belongs in a composition package or in
    the application layer, never in a direct sibling import.
    """
    siblings = {DISTRIBUTIONS[other] for other in ADAPTER_DISTRIBUTIONS if other != dist_name}
    offenders = [imp for imp in external_imports_of(dist_name) if imp.module in siblings]
    assert not offenders, f"{dist_name} must not import a sibling adapter:\n" + "\n".join(
        f"  {imp.where()} imports {imp.module!r}" for imp in offenders
    )


@pytest.mark.parametrize("dist_name", ADAPTER_DISTRIBUTIONS)
def test_adapter_declares_only_core_as_a_workspace_dependency(dist_name: str) -> None:
    """Packaging metadata must agree with the import rule."""
    declared = declared_workspace_dependencies(dist_name)
    assert declared == [CORE_DISTRIBUTION], (
        f"{dist_name} must declare exactly one workspace dependency "
        f"({CORE_DISTRIBUTION}); found {declared}"
    )


def test_http_openapi_projection_uses_only_stdlib_and_workspace_boundaries() -> None:
    """E6.7: generating OpenAPI must not require a protocol or UI library."""
    path = WORKSPACE_ROOT / "packages" / "agnara-http" / "src" / "agnara_http" / "_openapi.py"
    allowed = {CORE_IMPORT_NAME, DISTRIBUTIONS["agnara-http"]}
    offenders = [
        imported
        for imported in _file_imports(path)
        if imported.module not in allowed and not is_standard_library(imported.module)
    ]
    assert not offenders, "OpenAPI projection must stay dependency-free:\n" + "\n".join(
        f"  {imported.where()} imports {imported.module!r}" for imported in offenders
    )


# ---------------------------------------------------------------------------
# Rule 3 — no package cycles
# ---------------------------------------------------------------------------


def test_import_graph_is_acyclic() -> None:
    cycle = find_cycle(import_graph())
    assert cycle is None, "workspace import cycle: " + " -> ".join(cycle or [])


def test_declared_dependency_graph_is_acyclic() -> None:
    cycle = find_cycle(dependency_graph())
    assert cycle is None, "declared dependency cycle: " + " -> ".join(cycle or [])


def test_dependency_direction_points_inward() -> None:
    """Every workspace edge terminates at the core, never leaves it."""
    graph = dependency_graph()
    assert graph[CORE_DISTRIBUTION] == set(), (
        f"{CORE_DISTRIBUTION} must not depend on any workspace package; "
        f"found {sorted(graph[CORE_DISTRIBUTION])}"
    )
    for dist_name in ADAPTER_DISTRIBUTIONS:
        assert graph[dist_name] <= {CORE_DISTRIBUTION}, (
            f"{dist_name} may only depend on {CORE_DISTRIBUTION}; found {sorted(graph[dist_name])}"
        )


# ---------------------------------------------------------------------------
# Rule 4 — imports resolve to a known boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dist_name", sorted(DISTRIBUTIONS))
def test_package_has_no_unresolvable_workspace_import(dist_name: str) -> None:
    """An ``agnara``-prefixed import must name a real workspace package.

    This catches typos and stale renames that would otherwise only surface
    at runtime, long after the boundary was crossed.
    """
    known = set(DISTRIBUTIONS.values())
    offenders = [
        imp
        for imp in external_imports_of(dist_name)
        if imp.module.startswith("agnara") and imp.module not in known
    ]
    assert not offenders, f"{dist_name} imports an unknown agnara package:\n" + "\n".join(
        f"  {imp.where()} imports {imp.module!r}" for imp in offenders
    )


@pytest.mark.parametrize("dist_name", ADAPTER_DISTRIBUTIONS)
def test_adapter_may_import_the_core(dist_name: str) -> None:
    """A guard on the guards: the allowed edge must stay allowed.

    If this ever fails, the rules above have become stricter than
    ARCHITECTURE.md section 4 intends.
    """
    siblings = {DISTRIBUTIONS[other] for other in ADAPTER_DISTRIBUTIONS if other != dist_name}
    assert CORE_IMPORT_NAME not in siblings
    assert CORE_DISTRIBUTION in declared_dependencies(dist_name)


#: Browser documentation renderers and their runtimes. ADR 0018 keeps every
#: one of these behind the optional documentation-provider boundary, so
#: `agnara-http` must not acquire one as a dependency, not even a soft import.
FORBIDDEN_UI_PACKAGES = frozenset(
    {
        "swagger_ui",
        "swagger_ui_bundle",
        "flask_swagger_ui",
        "redoc",
        "redocly",
        "scalar",
        "scalar_fastapi",
        "rapidoc",
        "stoplight",
        "elements",
        "jinja2",
        "mako",
        "markupsafe",
    }
)


def test_the_http_adapter_imports_no_browser_documentation_package() -> None:
    offenders = [
        imported
        for imported in external_imports_of("agnara-http")
        if imported.module in FORBIDDEN_UI_PACKAGES
    ]
    assert not offenders, (
        "agnara-http imports a browser documentation package, which ADR 0018 "
        "keeps behind the optional provider boundary:\n"
        + "\n".join(f"  {imported.where}: {imported.module}" for imported in offenders)
    )


def test_the_http_adapter_declares_no_browser_documentation_dependency() -> None:
    declared = {
        _requirement_name(requirement) for requirement in declared_dependencies("agnara-http")
    }
    assert not declared & FORBIDDEN_UI_PACKAGES, (
        f"agnara-http declares a browser documentation dependency: "
        f"{sorted(declared & FORBIDDEN_UI_PACKAGES)}"
    )
