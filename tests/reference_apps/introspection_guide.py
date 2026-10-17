"""Check the exact filtered-discovery guide against candidate wheels under Python -I."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from agnara.execution import Failure, FailureCode, Success
from agnara.introspection import INTROSPECTION_FORMAT, INTROSPECTION_VERSION

VIEWS = {
    "anonymous": (["health"], ["http"]),
    "reader": (["health", "lookup"], ["http", "mcp"]),
    "identity_only": (["health", "lookup"], []),
    "disabled": ([], []),
    "listed_without_authority": (["health", "lookup", "refresh"], ["http", "mcp"]),
}


def expected_document(names: list[str], transports: list[str], *, identity: bool) -> dict:
    descriptions = {
        "health": "Report catalog health.",
        "lookup": "Read one catalog item.",
        "refresh": "Refresh the local demo cache.",
    }
    capabilities = []
    for name in names:
        transport = "http" if name == "health" else "mcp"
        capabilities.append(
            {
                "id": f"catalog.{name}",
                "description": None if identity else descriptions[name],
                "effects": [],
                "scopes": ["catalog:read"] if name == "lookup" and not identity else [],
                "risk": "low",
                "confirmation": "never",
                "idempotency": "unknown",
                "inputs": [{"name": "sku", "required": True, "schema": {"type": "string"}}]
                if name == "lookup" and not identity
                else [],
                "dependencies": [],
                "policies": [],
                "exposures": []
                if identity
                else [
                    {
                        "transport": transport,
                        "name": "GET /health" if name == "health" else f"catalog.{name}",
                        "detail": {},
                    }
                ],
                "transports": [] if identity else [transport],
            }
        )
    return {
        "format": INTROSPECTION_FORMAT,
        "version": INTROSPECTION_VERSION,
        "filtered": True,
        "project": None,
        "transports": transports,
        "applications": [
            {
                "name": "catalog",
                "transports": transports,
                "apps": [],
                "capabilities": capabilities,
                "providers": [],
            }
        ]
        if names
        else [],
    }


def canonical(value: Any) -> str:
    # JSON comparison separates integer 1 from the schema boolean true.
    return json.dumps(value, sort_keys=True)


def container_ids(value: Any) -> set[int]:
    """Collect mutable JSON containers, allowing shared immutable scalar values."""
    found: set[int] = set()
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, (dict, list)) and id(item) not in found:
            found.add(id(item))
            pending.extend(item.values() if isinstance(item, dict) else item)
    return found


def validate(demo: Any) -> None:
    source = demo["source"]
    assert source.filtered is False and len(source.applications) == 1
    app = source.applications[0]
    assert app.name == "catalog"
    assert [item.id for item in app.capabilities] == [
        "catalog.health",
        "catalog.lookup",
        "catalog.refresh",
    ]
    assert len(app.providers) == 1 and app.providers[0].provides.name == "Ledger"
    lookup = app.capabilities[1]
    assert len(lookup.dependencies) == 1 and lookup.dependencies[0].parameter == "ledger"
    assert lookup.dependencies[0].type == app.providers[0].provides
    assert [policy.kind for policy in lookup.policies] == ["ScopePolicy"]
    assert len(lookup.exposures) == 1
    assert lookup.exposures[0].json_data() == {
        "transport": "mcp",
        "name": "catalog.lookup",
        "detail": {"surface": "agents", "tool": "catalog.lookup"},
    }
    documents, views = demo["documents"], demo["views"]
    assert list(documents) == list(views) == list(VIEWS)
    expected = {
        name: expected_document(names, transports, identity=name == "identity_only")
        for name, (names, transports) in VIEWS.items()
    }
    assert canonical(documents) == canonical(expected)
    source_before = source.json_data()
    fresh = {name: view.json_data() for name, view in views.items()}
    assert all(view.filtered is True for view in views.values())
    assert canonical(fresh) == canonical(expected)
    # Detect aliasing before mutation, including shared empty nested containers.
    owned = container_ids(source_before)
    for document in [*documents.values(), *fresh.values()]:
        identifiers = container_ids(document)
        assert owned.isdisjoint(identifiers), "publication containers are shared"
        owned.update(identifiers)
    fresh["reader"]["applications"][0]["capabilities"][1]["inputs"][0]["schema"]["type"] = "forged"
    fresh["reader"]["applications"][0]["capabilities"][1]["exposures"][0]["detail"]["surface"] = (
        "forged"
    )
    fresh["anonymous"]["applications"].clear()
    assert canonical(source.json_data()) == canonical(source_before)
    assert canonical(documents) == canonical(expected)
    assert canonical({name: view.json_data() for name, view in views.items()}) == canonical(
        expected
    )
    assert demo["discovery_effects"] == demo["denied_effects"] == []
    assert list(demo["results"]) == ["denied", "hidden", "allowed"]
    denied = demo["results"]["denied"]
    assert isinstance(denied, Failure) and denied.code is FailureCode.FORBIDDEN
    assert denied == Failure(FailureCode.FORBIDDEN, "required scopes not granted")
    assert demo["results"]["hidden"] == Success("refreshed")
    assert demo["results"]["allowed"] == Success("Item A-1")
    assert demo["effects"] == [
        "resource.open",
        "refresh",
        "resource.close",
        "resource.open",
        "lookup:A-1",
        "resource.close",
    ]


async def run_guide(path: Path) -> Any:
    name = "_agnara_introspection_guide_consumer"
    assert name not in sys.modules
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        async with asyncio.timeout(20):
            demo = await module.bounded_demonstration()
        assert asyncio.all_tasks() == {asyncio.current_task()}, "guide tasks survived"
        return demo
    finally:
        del sys.modules[name]


if __name__ == "__main__":
    validate(asyncio.run(run_guide(Path(sys.argv[1]))))
    print("INTROSPECTION_GUIDE_ARTIFACT_OK")
