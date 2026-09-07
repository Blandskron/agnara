"""I9: the public core API is exact, classified and reviewable.

The manifest is checked twice on purpose. `scripts/check_release_readiness.py`
reads each module's literal ``__all__`` with `ast`, because a release gate must
not import the package it is judging. These tests import the modules, so they
also see what the source text cannot: whether every exported name is really
there.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT

MANIFEST = WORKSPACE_ROOT / "docs" / "public-api.json"
POLICY = WORKSPACE_ROOT / "docs" / "PUBLIC_API.md"
STABILITIES = {"stable", "provisional", "experimental", "internal"}


def document() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def modules() -> list[dict[str, Any]]:
    return document()["modules"]


MODULE_NAMES = [entry["module"] for entry in modules()]


def exports_of(module: str) -> list[dict[str, str]]:
    return next(entry for entry in modules() if entry["module"] == module)["exports"]


def test_manifest_identifies_its_contract() -> None:
    assert document()["schema_version"] == 2
    assert document()["distribution"] == "agnara"


def test_the_top_level_module_is_governed() -> None:
    """Every other module is optional to add; this one is the released surface."""
    assert "agnara" in MODULE_NAMES


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
def test_alpha_makes_no_stable_api_claim(module: str) -> None:
    assert {entry["stability"] for entry in exports_of(module)} == {"provisional"}


def test_policy_defines_every_stability_term() -> None:
    policy = POLICY.read_text(encoding="utf-8")

    for stability in STABILITIES:
        assert f"`{stability}`" in policy


def test_policy_names_the_machine_readable_inventory() -> None:
    assert "public-api.json" in POLICY.read_text(encoding="utf-8")


def test_policy_lists_every_governed_module() -> None:
    """The human-facing policy must not describe a smaller surface than the gate."""
    policy = POLICY.read_text(encoding="utf-8")

    for module in MODULE_NAMES:
        assert f"`{module}`" in policy, module
