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
def test_alpha_makes_no_stable_api_claim(module: str) -> None:
    """No symbol is `stable` merely because it is useful.

    A module that exports nothing -- a reserved namespace -- makes no claim at
    all, which is the honest classification for a package with no code.
    """
    assert {entry["stability"] for entry in exports_of(module)} <= {"provisional"}


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
