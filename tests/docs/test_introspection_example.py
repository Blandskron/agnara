"""The discovery guide keeps publication separate from execution authority."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from examples.introspection import Ledger, bounded_demonstration

from agnara.execution import Failure, FailureCode, Success
from agnara.introspection import INTROSPECTION_FORMAT, INTROSPECTION_VERSION


def test_introspection_example_filters_before_publication_without_effects() -> None:
    async def run():
        outcome = await bounded_demonstration()
        assert asyncio.all_tasks() == {asyncio.current_task()}
        return outcome

    outcome = asyncio.run(run())
    source = outcome["source"]
    assert not source.filtered
    assert [item.id for item in source.applications[0].capabilities] == [
        "catalog.health",
        "catalog.lookup",
        "catalog.refresh",
    ]
    assert source.applications[0].providers[0].provides.name == "Ledger"
    assert source.applications[0].capabilities[1].dependencies[0].parameter == "ledger"
    assert source.applications[0].capabilities[1].policies[0].kind == "ScopePolicy"
    assert source.applications[0].capabilities[1].exposures[0].json_data()["detail"] == {
        "surface": "agents",
        "tool": "catalog.lookup",
    }
    documents = outcome["documents"]
    for name, ids, transports in (
        ("anonymous", ["catalog.health"], ["http"]),
        ("reader", ["catalog.health", "catalog.lookup"], ["http", "mcp"]),
        ("identity_only", ["catalog.health", "catalog.lookup"], []),
        ("disabled", [], []),
    ):
        document = documents[name]
        assert document["format"] == INTROSPECTION_FORMAT
        assert document["version"] == INTROSPECTION_VERSION
        assert document["filtered"] is True
        assert document["transports"] == transports
        assert [
            item["id"] for app in document["applications"] for item in app["capabilities"]
        ] == ids
        serialized = json.dumps(document)
        assert "catalog.refresh" not in serialized
        assert Ledger.secret not in serialized
        assert "Ledger" not in serialized and "ScopePolicy" not in serialized
        for app in document["applications"]:
            assert app["providers"] == []
            for capability in app["capabilities"]:
                assert capability["dependencies"] == capability["policies"] == []
                assert all(exposure["detail"] == {} for exposure in capability["exposures"])
    assert "mcp" not in json.dumps(documents["anonymous"])
    assert documents["disabled"]["applications"] == []
    assert [
        item["id"]
        for item in documents["listed_without_authority"]["applications"][0]["capabilities"]
    ] == ["catalog.health", "catalog.lookup", "catalog.refresh"]
    lookup = documents["reader"]["applications"][0]["capabilities"][1]
    assert lookup["scopes"] == ["catalog:read"]
    assert lookup["inputs"] == [{"name": "sku", "required": True, "schema": {"type": "string"}}]
    assert lookup["exposures"] == [{"transport": "mcp", "name": "catalog.lookup", "detail": {}}]
    identity = documents["identity_only"]["applications"][0]["capabilities"][1]
    assert identity["description"] is None
    assert identity["inputs"] == identity["scopes"] == identity["exposures"] == []
    assert outcome["discovery_effects"] == outcome["denied_effects"] == []
    assert isinstance(outcome["results"]["denied"], Failure)
    assert outcome["results"]["denied"].code is FailureCode.FORBIDDEN
    assert outcome["results"]["hidden"] == Success("refreshed")
    assert outcome["results"]["allowed"] == Success("Item A-1")
    assert outcome["effects"] == [
        "resource.open",
        "refresh",
        "resource.close",
        "resource.open",
        "lookup:A-1",
        "resource.close",
    ]
    # Every viewer starts from the same original model. Publishing one view
    # must neither replace that model nor leave serialized containers shared.
    before = source.json_data()
    lookup["inputs"][0]["schema"]["type"] = "forged"
    lookup["exposures"][0]["detail"]["surface"] = "forged"
    documents["anonymous"]["applications"].clear()
    assert source.json_data() == before
    assert outcome["views"]["reader"].json_data()["applications"][0]["capabilities"][1]["inputs"][
        0
    ]["schema"] == {"type": "string"}
    assert outcome["views"]["anonymous"].json_data()["applications"]


def test_introspection_example_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "introspection.py"
    completed = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "anonymous: ['catalog.health']; transports=['http']",
        "reader: ['catalog.health', 'catalog.lookup']; transports=['http', 'mcp']",
        "identity_only: ['catalog.health', 'catalog.lookup']; transports=[]",
        "disabled: []; transports=[]",
        "listed_without_authority: ['catalog.health', 'catalog.lookup', 'catalog.refresh']; "
        "transports=['http', 'mcp']",
        "denied: forbidden",
        "hidden: refreshed",
        "allowed: Item A-1",
        "discovery_effects: []",
        "denied_effects: []",
        "effects: ['resource.open', 'refresh', 'resource.close', 'resource.open', "
        "'lookup:A-1', 'resource.close']",
    ]
