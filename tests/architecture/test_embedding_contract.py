"""Architecture evidence for the framework-neutral embedding boundary."""

from __future__ import annotations

import json
from pathlib import Path

from tests.architecture.boundaries import (
    CORE_DISTRIBUTION,
    FORBIDDEN_IN_CORE,
    WORKSPACE_ROOT,
    external_imports_of,
)

ADR = WORKSPACE_ROOT / "docs" / "adr" / "0094-framework-neutral-embedding-contract.md"
INTEROPERABILITY = WORKSPACE_ROOT / "docs" / "INTEROPERABILITY.md"
MATURITY = WORKSPACE_ROOT / "docs" / "MATURITY.md"
PUBLIC_API = WORKSPACE_ROOT / "docs" / "PUBLIC_API.md"
RELEASE_STATUS = WORKSPACE_ROOT / "docs" / "releases" / "release-status.json"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _exports(module: str) -> set[str]:
    manifest = json.loads(_text(WORKSPACE_ROOT / "docs" / "public-api.json"))
    for distribution in manifest["distributions"]:
        for entry in distribution["modules"]:
            if entry["module"] == module:
                return {export["name"] for export in entry["exports"]}
    raise AssertionError(f"missing governed module {module!r}")


def test_embedding_contract_is_accepted_but_does_not_claim_host_support() -> None:
    adr = _text(ADR)

    assert "- Status: Accepted" in adr
    assert "does not claim concrete framework support" in adr
    assert "Version-pinned framework fixtures" in adr
    assert "framework-specific HostApp in core" in adr


def test_contract_uses_existing_provisional_public_surface_without_new_exports() -> None:
    public_api = _text(PUBLIC_API)

    assert "ADR 0094 selects no new host API." in public_api
    assert {"Agnara"} <= _exports("agnara")
    assert {"DIContainer", "DIRegistry"} <= _exports("agnara.core.di")
    assert {
        "CapabilityRuntime",
        "ExecutionContext",
        "ExecutionPlan",
        "Failure",
        "Invocation",
        "Success",
    } <= _exports("agnara.execution")


def test_core_remains_free_of_framework_dependencies() -> None:
    offenders = [
        imported
        for imported in external_imports_of(CORE_DISTRIBUTION)
        if imported.module in FORBIDDEN_IN_CORE
    ]

    assert not offenders


def test_four_modes_share_one_value_only_contract_example() -> None:
    adr = _text(ADR)
    contract = _text(INTEROPERABILITY)

    for mode in (
        "Standalone",
        "Agnara host",
        "Embedded Agnara",
        "Side-by-side",
    ):
        assert f"| {mode} |" in adr
        assert f"| {mode} |" in contract
    assert "async def invoke_from_host" in adr
    assert "does not import a host package into core tests" in adr
    assert "Raw request/response/session" in adr
    assert "Idempotency is never authorization to retry." in contract


def test_status_records_design_evidence_without_closing_interoperability() -> None:
    status = json.loads(_text(RELEASE_STATUS))
    interoperability = next(gate for gate in status["gates"] if gate["id"] == "interoperability")

    assert "Framework embedding contract" in _text(MATURITY)
    assert "DESIGNED" in _text(MATURITY)
    assert interoperability["status"] == "NEEDS_REVIEW"
    assert "Version-pinned host fixtures" in interoperability["detail"]
