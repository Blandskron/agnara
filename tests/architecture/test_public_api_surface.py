"""I9: the top-level core API is exact, classified and reviewable."""

from __future__ import annotations

import json
from typing import Any

import agnara
from tests.architecture.boundaries import WORKSPACE_ROOT

MANIFEST = WORKSPACE_ROOT / "docs" / "public-api.json"
POLICY = WORKSPACE_ROOT / "docs" / "PUBLIC_API.md"
STABILITIES = {"stable", "provisional", "experimental", "internal"}


def document() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def exports() -> list[dict[str, str]]:
    return document()["exports"]


def test_manifest_identifies_its_contract() -> None:
    assert document()["schema_version"] == 1
    assert document()["distribution"] == "agnara"
    assert document()["module"] == "agnara"


def test_every_entry_has_one_name_and_one_known_stability() -> None:
    for entry in exports():
        assert set(entry) == {"name", "stability"}
        assert entry["name"]
        assert entry["stability"] in STABILITIES
        assert entry["stability"] != "internal", (
            "an internal name belongs outside __all__ and the public manifest"
        )


def test_every_export_is_classified_exactly_once_and_in_order() -> None:
    classified = [entry["name"] for entry in exports()]

    assert len(classified) == len(set(classified))
    assert classified == agnara.__all__


def test_alpha_makes_no_stable_api_claim() -> None:
    assert {entry["stability"] for entry in exports()} == {"provisional"}


def test_policy_defines_every_stability_term() -> None:
    policy = POLICY.read_text(encoding="utf-8")

    for stability in STABILITIES:
        assert f"`{stability}`" in policy


def test_policy_names_the_machine_readable_inventory() -> None:
    assert "public-api.json" in POLICY.read_text(encoding="utf-8")
