"""Check the exact copied provisional events example against installed wheels."""

from __future__ import annotations

import asyncio
import json
import runpy
import sys
from pathlib import Path
from typing import Any


def validate(outcome: dict[str, Any]) -> None:
    assert outcome["surface_count"] == 1
    assert outcome["asyncapi"] == "3.1.0"
    assert outcome["diagnostics"] == [
        ("success", "acknowledge"),
        ("conflict", "reject"),
        ("invalid_input", "reject"),
        ("type_mismatch", "reject"),
        ("internal_failure", "release"),
        ("cancelled", "release"),
    ]
    assert outcome["events"] == [
        "ledger.open",
        "apply:A-1:9007199254740993:ok",
        "ledger.close",
        "delivery.acknowledge",
        "ledger.open",
        "apply:A-1:9007199254740993:conflict",
        "ledger.close",
        "delivery.reject",
        # Lexically integral 2.0 and wrong CloudEvents type must not acquire Ledger.
        "delivery.reject",
        "delivery.reject",
        "ledger.open",
        "apply:A-1:2:transient",
        "ledger.close",
        "delivery.release",
        "ledger.open",
        "apply:A-2:9007199254740994:block",
        "ledger.close",
        "delivery.release",
        "container.close",
    ]
    assert "private-broker-diagnostic-must-be-redacted" not in json.dumps(outcome)

    doc = outcome["doc"]
    assert doc["asyncapi"] == "3.1.0"
    assert "servers" not in doc
    assert doc["defaultContentType"] == "application/cloudevents+json"
    channel = doc["channels"]["inventory-apply"]
    assert channel["address"] == "inventory.snapshot.v1"
    operation = doc["operations"]["receive_inventory-apply"]
    assert operation["action"] == "receive"
    assert operation["channel"] == {"$ref": "#/channels/inventory-apply"}
    assert operation["messages"] == [
        {"$ref": "#/channels/inventory-apply/messages/inventory-applyMessage"}
    ]
    message = doc["components"]["messages"]["inventory-applyMessage"]
    assert message["payload"]["schemaFormat"] == "application/schema+json;version=draft-07"
    data_props = message["payload"]["schema"]["properties"]["data"]["properties"]
    assert "ledger" not in data_props
    assert set(data_props) == {"sku", "revision", "mode"}


async def run_guide(path: Path) -> dict[str, Any]:
    namespace = runpy.run_path(str(path))
    before = asyncio.all_tasks()
    async with asyncio.timeout(20):
        outcome = await namespace["demonstrate"]()
    assert asyncio.all_tasks() == before, "Events guide tasks survived teardown"
    return outcome


if __name__ == "__main__":
    validate(asyncio.run(run_guide(Path(sys.argv[1]))))
    print("EVENTS_GUIDE_ARTIFACT_OK")
