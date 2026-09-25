"""I9: the public API of every shipped distribution is exact and classified.

The manifest is checked twice on purpose. `scripts/check_release_readiness.py`
reads each module's literal ``__all__`` with `ast`, because a release gate must
not import the package it is judging. These tests import the modules, so they
also see what the source text cannot: whether every exported name is really
there.

The governed surface is the whole workspace, not the kernel. An application
consuming Agnara from outside this repository imports `agnara_http` and
`agnara_mcp` as readily as `agnara`, so a governed core beside an ungoverned
adapter is not a governed framework (ADR 0076).
"""

from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from typing import Any

import pytest

from tests.architecture.boundaries import DISTRIBUTIONS, WORKSPACE_ROOT

MANIFEST = WORKSPACE_ROOT / "docs" / "public-api.json"
POLICY = WORKSPACE_ROOT / "docs" / "PUBLIC_API.md"
REFERENCE = WORKSPACE_ROOT / "docs" / "API_REFERENCE.md"
REFERENCE_RENDERER = WORKSPACE_ROOT / "scripts" / "render_public_api_reference.py"
STABILITIES = {"stable", "provisional", "experimental", "internal"}


def document() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def distributions() -> list[dict[str, Any]]:
    return document()["distributions"]


DISTRIBUTION_NAMES = [entry["distribution"] for entry in distributions()]

#: (distribution, module) for every classified module, so a failure names both.
GOVERNED = [
    (entry["distribution"], module["module"])
    for entry in distributions()
    for module in entry["modules"]
]

MODULE_NAMES = [module for _, module in GOVERNED]


def exports_of(module: str) -> list[dict[str, str]]:
    return next(
        item for entry in distributions() for item in entry["modules"] if item["module"] == module
    )["exports"]


def test_manifest_identifies_its_contract() -> None:
    assert document()["schema_version"] == 3


def test_every_shipped_distribution_is_governed() -> None:
    """A package nobody classified is a package nobody reviewed."""
    assert set(DISTRIBUTION_NAMES) == set(DISTRIBUTIONS)


def test_no_distribution_is_classified_twice() -> None:
    assert len(DISTRIBUTION_NAMES) == len(set(DISTRIBUTION_NAMES))


@pytest.mark.parametrize("entry", distributions(), ids=DISTRIBUTION_NAMES)
def test_each_distribution_governs_its_own_entry_point(entry: dict[str, Any]) -> None:
    """Every other module is optional to add; this one is the released surface."""
    import_name = entry["import_name"]

    assert DISTRIBUTIONS[entry["distribution"]] == import_name
    assert import_name in [module["module"] for module in entry["modules"]]


@pytest.mark.parametrize(("distribution", "module"), GOVERNED)
def test_a_module_is_governed_by_the_distribution_that_ships_it(
    distribution: str, module: str
) -> None:
    assert module.split(".")[0] == DISTRIBUTIONS[distribution]


def test_no_module_is_classified_twice() -> None:
    assert len(MODULE_NAMES) == len(set(MODULE_NAMES))


@pytest.mark.parametrize("module", MODULE_NAMES)
def test_every_entry_has_one_name_and_one_known_stability(module: str) -> None:
    for entry in exports_of(module):
        assert set(entry) == {"name", "stability"}
        assert entry["name"]
        assert entry["stability"] in STABILITIES
        assert entry["stability"] != "internal", (
            "an internal name belongs outside __all__ and the public manifest"
        )


@pytest.mark.parametrize("module", MODULE_NAMES)
def test_every_export_is_classified_exactly_once_and_in_order(module: str) -> None:
    classified = [entry["name"] for entry in exports_of(module)]

    assert len(classified) == len(set(classified))
    assert classified == list(importlib.import_module(module).__all__)


@pytest.mark.parametrize("module", MODULE_NAMES)
def test_every_exported_name_actually_exists(module: str) -> None:
    """A name in ``__all__`` that the module does not define is a broken export.

    Neither the manifest nor the literal ``__all__`` can see this: both read
    the same list. Only importing does.
    """
    imported = importlib.import_module(module)
    missing = [name for name in imported.__all__ if not hasattr(imported, name)]

    assert not missing, f"{module} exports names it does not define: {missing}"


@pytest.mark.parametrize(
    ("module", "name"),
    (
        ("agnara", "JsonSchema"),
        ("agnara.execution", "IdempotencyConflictError"),
        ("agnara.introspection", "VisibilityRule"),
        ("agnara_mcp", "McpPrincipalMapper"),
        ("agnara_telemetry", "OpenTelemetryTracingHook"),
    ),
)
def test_representative_pre_stable_names_import_from_their_canonical_modules(
    module: str, name: str
) -> None:
    """Previously uncovered names remain direct public imports."""
    assert hasattr(importlib.import_module(module), name)


@pytest.mark.parametrize("module", MODULE_NAMES)
def test_no_public_name_is_underscore_prefixed(module: str) -> None:
    """`__version__` is the one dunder a distribution may publish."""
    offenders = [
        entry["name"]
        for entry in exports_of(module)
        if entry["name"].startswith("_") and entry["name"] != "__version__"
    ]

    assert not offenders, f"{module} publishes private-looking names: {offenders}"


@pytest.mark.parametrize("module", MODULE_NAMES)
def test_every_governed_export_is_stable(module: str) -> None:
    """The 1.0 surface contains only deliberate canonical commitments."""
    assert {entry["stability"] for entry in exports_of(module)} <= {"stable"}


def test_policy_defines_every_stability_term() -> None:
    policy = POLICY.read_text(encoding="utf-8")

    for stability in STABILITIES:
        assert f"`{stability}`" in policy


def test_policy_names_the_machine_readable_inventory() -> None:
    assert "public-api.json" in POLICY.read_text(encoding="utf-8")


def test_generated_reference_matches_the_manifest() -> None:
    """The reader-facing inventory is a projection, never a second manifest."""
    completed = subprocess.run(
        [sys.executable, str(REFERENCE_RENDERER), "--check"],
        cwd=WORKSPACE_ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "API_REFERENCE.md" in POLICY.read_text(encoding="utf-8")
    assert REFERENCE.is_file()


@pytest.mark.parametrize("distribution", DISTRIBUTION_NAMES)
def test_policy_lists_every_governed_distribution(distribution: str) -> None:
    assert f"`{distribution}`" in POLICY.read_text(encoding="utf-8")


@pytest.mark.parametrize("module", MODULE_NAMES)
def test_policy_lists_every_governed_module(module: str) -> None:
    """The human-facing policy must not describe a smaller surface than the gate."""
    policy = POLICY.read_text(encoding="utf-8")

    assert f"`{module}`" in policy, module


# ---------------------------------------------------------------------------
# Documentation may not state a count the manifest contradicts
# ---------------------------------------------------------------------------

#: Documents allowed to quote a public-surface size. A document not listed here
#: is not forbidden from existing; it is forbidden from carrying a number that
#: silently rots.
COUNTED_DOCUMENTS = (
    "docs/PUBLIC_API.md",
    "docs/MATURITY.md",
    "docs/TARGET_ARCHITECTURE.md",
    "docs/releases/RELEASE_CHECKLIST.md",
)

#: "337 exports", "337 classified exports", "337 governed exports", ...
_EXPORT_COUNT = re.compile(r"(\d[\d,]*)\s+(?:\w+\s+){0,2}exports\b")
#: "across 49 modules", "49 governed modules"
_MODULE_COUNT = re.compile(r"(\d[\d,]*)\s+(?:\w+\s+){0,1}modules\b")
#: Only the exact phrase used for the surface figure. Prose such as "dropped
#: from 17 public names to 4" is a historical fact about one distribution, not
#: a claim about the current surface, and this gate must not police it.
_NAME_COUNT = re.compile(r"(\d[\d,]*)\s+distinct\s+names\b")


def _surface_totals() -> tuple[int, int, int]:
    """Return (export paths, modules, distinct names) from the manifest."""
    paths = 0
    modules = 0
    names: set[tuple[str, str]] = set()
    for entry in distributions():
        for module in entry["modules"]:
            modules += 1
            for export in module["exports"]:
                paths += 1
                names.add((entry["distribution"], export["name"]))
    return paths, modules, len(names)


def _numbers(pattern: re.Pattern[str], text: str) -> set[int]:
    return {int(match.replace(",", "")) for match in pattern.findall(text)}


@pytest.mark.parametrize("relative", COUNTED_DOCUMENTS)
def test_no_document_states_a_public_surface_count_the_manifest_contradicts(
    relative: str,
) -> None:
    """One manifest, one set of numbers.

    `docs/MATURITY.md` said 324 exports, `docs/releases/RELEASE_CHECKLIST.md` said
    292, `docs/TARGET_ARCHITECTURE.md` said 292 across 48 modules, and the
    manifest said 337 across 49. Four documents, four answers, no way for a
    reader to know which to trust. Counts written by hand drift the moment an
    export is added, so the gate reads them back.
    """
    paths, modules, names = _surface_totals()
    text = (WORKSPACE_ROOT / relative).read_text(encoding="utf-8")

    stale_exports = _numbers(_EXPORT_COUNT, text) - {paths}
    stale_modules = _numbers(_MODULE_COUNT, text) - {modules}
    stale_names = _numbers(_NAME_COUNT, text) - {names}

    assert not stale_exports, (
        f"{relative} states {sorted(stale_exports)} exports; the manifest has {paths}"
    )
    assert not stale_modules, (
        f"{relative} states {sorted(stale_modules)} modules; the manifest has {modules}"
    )
    assert not stale_names, (
        f"{relative} states {sorted(stale_names)} distinct names; the manifest has {names}"
    )


def test_the_owning_document_states_the_current_count() -> None:
    """A gate that only rejects wrong numbers passes when every number is deleted."""
    paths, modules, names = _surface_totals()
    text = (WORKSPACE_ROOT / "docs" / "PUBLIC_API.md").read_text(encoding="utf-8")
    assert paths in _numbers(_EXPORT_COUNT, text)
    assert modules in _numbers(_MODULE_COUNT, text)
    assert names in _numbers(_NAME_COUNT, text)


def test_each_stable_name_has_one_canonical_import_path() -> None:
    """Alias paths are not part of the 1.x compatibility commitment."""
    paths, _modules, names = _surface_totals()
    assert names == paths
