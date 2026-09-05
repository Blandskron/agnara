"""The HTTP discovery endpoint and ``agnara inspect --json`` answer identically.

E8.6 requires "the same versioned serialization as CLI JSON". That is a claim
about two packages, so it is tested where both may be imported rather than
inside either one. The wire forms differ deliberately — the CLI indents for a
reader, the endpoint compacts for a client — so the assertion is on the
document, not on the bytes.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from agnara.execution import ExecutionPlan
from agnara.introspection import (
    DiscoveryVisibility,
    ScopeVisible,
    describe_app,
    snapshot,
)
from agnara.policy import Principal
from agnara_cli import main
from agnara_http._discovery import _compile_discovery, _DiscoveryDispatcher, _DiscoveryRoute
from agnara_http._dispatch import _compile_exposures

PATH = "/.well-known/agnara-capabilities"

APPLICATION = '''
from agnara import Agnara, Risk
from agnara.core.di import DIRegistry

registry = DIRegistry()
app = Agnara("billing")


@app.capability(scopes={"billing:write"}, risk=Risk.HIGH, effects={"financial-write"})
def refund(payment_id: str, amount_cents: int = 0) -> str:
    """Refund a captured payment."""
    return "refunded"


@app.capability
def health() -> str:
    """Report service health."""
    return "ok"
'''


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    (tmp_path / "shared.py").write_text(APPLICATION, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        yield tmp_path
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("shared", None)


def _shared() -> Any:
    """The application module the fixture wrote, imported the way the CLI does.

    Dynamically, because it exists only for the duration of one test and a
    static import would be a lie about the source tree.
    """
    return importlib.import_module("shared")


def served(visibility: DiscoveryVisibility, principal: Principal) -> dict[str, Any]:
    """Fetch the endpoint's document for one viewer."""
    shared = _shared()

    plans = [
        ExecutionPlan.compile(shared.app.capabilities[key], shared.registry)
        for key in shared.app.capabilities
    ]
    described = snapshot([describe_app(shared.app, plans, dependencies=shared.registry)])
    dispatcher = _DiscoveryDispatcher(
        _compile_discovery(
            _DiscoveryRoute(
                path=PATH,
                snapshot=described,
                visibility=visibility,
                principals=lambda scope: principal,
                challenge="Bearer",
            ),
            _compile_exposures(()),
        ),
        _unreachable,
    )
    events: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    asyncio.run(
        dispatcher(
            {
                "type": "http",
                "method": "GET",
                "path": PATH,
                "raw_path": PATH.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": [],
            },
            receive,
            send,
        )
    )
    body = b"".join(
        event.get("body", b"") for event in events if event["type"] == "http.response.body"
    )
    return json.loads(body.decode("utf-8"))


async def _unreachable(scope: Any, receive: Any, send: Any) -> None:  # pragma: no cover
    raise AssertionError("the discovery path must not fall through")


def exported(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> dict[str, Any]:
    code = main(["inspect", "shared:app", "--path", str(project), "--json", *arguments])
    assert code == 0
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    ("posture", "flag"),
    [("agent_safe", "agent"), ("identity_only", "identity"), ("unrestricted", "full")],
)
def test_both_surfaces_publish_the_same_document_for_one_viewer(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    posture: str,
    flag: str,
) -> None:
    visibility = getattr(DiscoveryVisibility, posture)(ScopeVisible())
    principal = Principal("viewer", scopes={"billing:write"})

    over_http = served(visibility, principal)
    from_cli = exported(project, capsys, "--visibility", flag, "--as-scope", "billing:write")

    assert over_http == from_cli
    assert over_http["format"] == "agnara-introspection"
    assert over_http["filtered"] is True


def test_both_surfaces_hide_the_same_capability_from_an_unscoped_viewer(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    visibility = DiscoveryVisibility.agent_safe(ScopeVisible())

    over_http = served(visibility, Principal("viewer", scopes={"other:read"}))
    from_cli = exported(project, capsys, "--visibility", "agent", "--as-scope", "other:read")

    identifiers = [
        capability["id"] for app in over_http["apps"] for capability in app["capabilities"]
    ]
    assert identifiers == ["billing.health"]
    assert over_http == from_cli


def test_the_two_wire_forms_differ_only_in_whitespace(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    visibility = DiscoveryVisibility.agent_safe(ScopeVisible())
    principal = Principal("viewer", scopes={"billing:write"})

    document = served(visibility, principal)
    compact = json.dumps(document, sort_keys=True, separators=(",", ":"))
    indented = json.dumps(document, indent=2, sort_keys=True)

    assert compact != indented
    assert json.loads(compact) == json.loads(indented)
    # The CLI's own output is the indented form of the same document.
    assert (
        json.dumps(
            exported(project, capsys, "--visibility", "agent", "--as-scope", "billing:write"),
            indent=2,
            sort_keys=True,
        )
        == indented
    )


def test_neither_surface_can_be_told_a_snapshot_is_already_filtered(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mark comes from filtering, so an unfiltered document cannot claim it."""
    shared = _shared()

    plans = [
        ExecutionPlan.compile(shared.app.capabilities[key], shared.registry)
        for key in shared.app.capabilities
    ]
    unfiltered = snapshot([describe_app(shared.app, plans)])

    assert unfiltered.json_data()["filtered"] is False
    assert (
        served(
            DiscoveryVisibility.identity_only(ScopeVisible()),
            Principal("viewer"),
        )["filtered"]
        is True
    )
    assert exported(project, capsys, "--visibility", "identity")["filtered"] is True
