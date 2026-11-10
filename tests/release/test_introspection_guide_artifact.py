"""Negative proofs for the installed filtered-introspection guide consumer."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from agnara.execution import Success
from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.introspection_guide import VIEWS, canonical, run_guide, validate


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "introspection.py"))


def clone(demo):
    return {
        **demo,
        "documents": deepcopy(demo["documents"]),
        "views": dict(demo["views"]),
        "results": dict(demo["results"]),
        "discovery_effects": list(demo["discovery_effects"]),
        "denied_effects": list(demo["denied_effects"]),
        "effects": list(demo["effects"]),
    }


def test_actual_guide_passes_repeatedly_without_mutating_publications(demonstrated) -> None:
    before = canonical(demonstrated["documents"])
    validate(demonstrated)
    validate(demonstrated)
    assert canonical(demonstrated["documents"]) == before


@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize(
    "field,value", [("format", "wrong"), ("filtered", 1), ("transports", ["wrong"])]
)
def test_changed_publication_metadata_is_rejected(demonstrated, view, field, value) -> None:
    changed = clone(demonstrated)
    changed["documents"][view][field] = value
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize(
    "case", ["providers", "dependencies", "policies", "detail", "secret", "scopes", "schema"]
)
def test_reader_internal_leaks_and_contract_changes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    app = changed["documents"]["reader"]["applications"][0]
    item = app["capabilities"][1]
    if case == "providers":
        app["providers"] = ["Ledger"]
    elif case in {"dependencies", "policies"}:
        item[case] = ["ScopePolicy"]
    elif case == "detail":
        item["exposures"][0]["detail"] = {"surface": "agents"}
    elif case == "secret":
        item["runtime"] = "demo-runtime-secret"
    elif case == "scopes":
        item["scopes"] = []
    else:
        item["inputs"][0]["required"] = 1
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("field", ["description", "inputs", "scopes", "exposures"])
def test_identity_only_metadata_is_rejected(demonstrated, field) -> None:
    changed = clone(demonstrated)
    changed["documents"]["identity_only"]["applications"][0]["capabilities"][1][field] = "leaked"
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["denied", "hidden", "allowed"])
def test_changed_invocation_outcomes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    changed["results"][case] = Success("wrong")
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize(
    "case", ["discovery_effects", "denied_effects", "extra", "missing", "order"]
)
def test_effects_and_teardown_changes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    if case in {"discovery_effects", "denied_effects"}:
        changed[case].append("resource.open")
    elif case == "extra":
        changed["effects"].append("lookup:unapproved")
    elif case == "missing":
        changed["effects"].remove("resource.close")
    else:
        changed["effects"].reverse()
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["filtered", "provider", "capabilities"])
def test_corrupt_source_descriptors_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    source = changed["source"]
    if case == "filtered":
        changed["source"] = replace(source, filtered=True)
    else:
        app = source.applications[0]
        app = replace(app, **({"providers": ()} if case == "provider" else {"capabilities": ()}))
        changed["source"] = replace(source, applications=(app,))
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["publications", "view"])
def test_serialization_aliases_are_rejected_before_mutation(demonstrated, case) -> None:
    changed = clone(demonstrated)
    documents = changed["documents"]
    if case == "publications":
        documents["reader"]["applications"][0]["providers"] = documents["anonymous"][
            "applications"
        ][0]["providers"]
    else:
        changed["views"]["reader"] = SimpleNamespace(
            filtered=True, json_data=lambda: documents["reader"]
        )
    before = canonical(documents)
    with pytest.raises(AssertionError, match="containers are shared"):
        validate(changed)
    assert canonical(documents) == before
