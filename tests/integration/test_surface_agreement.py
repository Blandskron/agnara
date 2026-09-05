"""Every surface describes one application the same way, for one viewer.

Six surfaces now answer questions about a compiled application: the CLI's text,
JSON, graph and context renderings, the HTTP discovery endpoint, and MCP
``tools/list``. The first five share a snapshot and a filter by construction.
MCP does not: its scope filter was written before the introspection layer
existed, on its own code path.

Each agreement rests on a convention. This module turns the conventions into
assertions, so a change that breaks one fails here rather than in a client that
trusted whichever surface it happened to read.
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
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from agnara.execution import ExecutionPlan
from agnara.introspection import (
    DiscoveryVisibility,
    ScopeVisible,
    describe_app,
    filter_snapshot,
    snapshot,
)
from agnara.policy import Principal
from agnara_cli import EXIT_OK, main
from agnara_http._discovery import _compile_discovery, _DiscoveryDispatcher, _DiscoveryRoute
from agnara_http._dispatch import _compile_exposures
from agnara_mcp import Mcp, McpAuthenticatedIdentity, McpAuthorization

PATH = "/.well-known/agnara-capabilities"

APPLICATION = '''
from agnara import Agnara, Confirmation, Risk
from agnara.core.di import DIRegistry

registry = DIRegistry()
app = Agnara("billing")


@app.capability(
    scopes={"billing:write"},
    effects={"financial-write"},
    risk=Risk.HIGH,
    confirmation=Confirmation.NEVER,
    idempotent=False,
)
def refund(payment_id: str) -> str:
    """Refund a captured payment."""
    return "refunded"


@app.capability(scopes={"billing:read"})
def statement(account_id: str) -> str:
    """Read an account statement."""
    return "statement"


@app.capability
def health() -> str:
    """Report service health."""
    return "ok"
'''

#: Viewers whose visible set every surface must agree on.
VIEWERS: dict[str, frozenset[str]] = {
    "anonymous": frozenset(),
    "reader": frozenset({"billing:read"}),
    "writer": frozenset({"billing:write"}),
    "both": frozenset({"billing:read", "billing:write"}),
}


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    (tmp_path / "surfaces.py").write_text(APPLICATION, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        yield tmp_path
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("surfaces", None)


def loaded() -> Any:
    return importlib.import_module("surfaces")


def built() -> Any:
    module = loaded()
    plans = [
        ExecutionPlan.compile(module.app.capabilities[key], module.registry)
        for key in module.app.capabilities
    ]
    return snapshot([describe_app(module.app, plans, dependencies=module.registry)])


def visibility() -> DiscoveryVisibility:
    return DiscoveryVisibility.agent_safe(ScopeVisible())


def principal(scopes: frozenset[str]) -> Principal:
    return Principal("viewer", scopes=scopes)


# --- the five snapshot surfaces -------------------------------------------


def from_model(scopes: frozenset[str]) -> list[str]:
    document = filter_snapshot(built(), visibility(), principal(scopes)).json_data()
    return [item["id"] for app in document["apps"] for item in app["capabilities"]]


def from_cli_json(project: Path, capsys: Any, scopes: frozenset[str]) -> dict[str, Any]:
    arguments = [argument for scope in sorted(scopes) for argument in ("--as-scope", scope)]
    if not scopes:
        # Without a scope the CLI shows everything, so simulate an anonymous
        # viewer by naming a scope the application never declares.
        arguments = ["--as-scope", "nothing:granted"]
    assert (
        main(
            [
                "inspect",
                "surfaces:app",
                "--path",
                str(project),
                "--dependencies",
                "registry",
                "--visibility",
                "agent",
                "--json",
                *arguments,
            ]
        )
        == EXIT_OK
    )
    return json.loads(capsys.readouterr().out)


def from_cli_command(project: Path, capsys: Any, scopes: frozenset[str], command: str) -> str:
    arguments = [argument for scope in sorted(scopes) for argument in ("--as-scope", scope)]
    if not scopes:
        arguments = ["--as-scope", "nothing:granted"]
    assert (
        main(
            [
                command,
                "surfaces:app",
                "--path",
                str(project),
                "--dependencies",
                "registry",
                "--visibility",
                "agent",
                *arguments,
            ]
        )
        == EXIT_OK
    )
    return capsys.readouterr().out


def from_http(scopes: frozenset[str]) -> dict[str, Any]:
    dispatcher = _DiscoveryDispatcher(
        _compile_discovery(
            _DiscoveryRoute(
                path=PATH,
                snapshot=built(),
                visibility=visibility(),
                principals=lambda scope: principal(scopes),
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


def identifiers(document: dict[str, Any]) -> list[str]:
    return [item["id"] for app in document["apps"] for item in app["capabilities"]]


@pytest.mark.parametrize("viewer", sorted(VIEWERS))
def test_every_snapshot_surface_shows_one_viewer_the_same_capabilities(
    project: Path, capsys: pytest.CaptureFixture[str], viewer: str
) -> None:
    scopes = VIEWERS[viewer]
    expected = from_model(scopes)

    assert identifiers(from_cli_json(project, capsys, scopes)) == expected
    assert identifiers(from_http(scopes)) == expected
    for command in ("inspect", "graph", "context"):
        rendered = from_cli_command(project, capsys, scopes, command)
        for capability_id in expected:
            assert capability_id in rendered, (command, capability_id)
        for hidden in set(from_model(frozenset(VIEWERS["both"]))) - set(expected):
            assert hidden not in rendered, (command, hidden)


@pytest.mark.parametrize("viewer", sorted(VIEWERS))
def test_the_cli_and_the_endpoint_publish_the_identical_document(
    project: Path, capsys: pytest.CaptureFixture[str], viewer: str
) -> None:
    scopes = VIEWERS[viewer]

    assert from_cli_json(project, capsys, scopes) == from_http(scopes)


def test_every_surface_carries_the_snapshot_provenance(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scopes = VIEWERS["both"]

    for document in (from_cli_json(project, capsys, scopes), from_http(scopes)):
        assert document["format"] == "agnara-introspection"
        assert document["version"] == "0"
        assert document["filtered"] is True

    context = from_cli_command(project, capsys, scopes, "context")
    assert "`agnara-introspection` version `0`" in context


def test_no_surface_publishes_a_field_the_decision_withheld(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`agent_safe` withholds dependencies, providers and policies."""
    scopes = VIEWERS["both"]
    encoded = from_cli_json(project, capsys, scopes)

    for app in encoded["apps"]:
        assert app["providers"] == []
        for capability in app["capabilities"]:
            assert capability["dependencies"] == []
            assert capability["policies"] == []
    assert from_http(scopes) == encoded

    graph = from_cli_command(project, capsys, scopes, "graph")
    assert "withheld relationship sources: dependencies, providers" in graph


# --- the surface that does not share the snapshot --------------------------


def mcp_visible(scopes: frozenset[str]) -> list[str]:
    """What MCP `tools/list` would show, through MCP's own filter.

    This calls `discoverable_tool_names`, the function the discovery server
    actually uses, with the SDK's verified-identity ContextVar set the way an
    authenticated request sets it. Reimplementing the comparison here would
    make the test agree with itself rather than with MCP.
    """
    module = loaded()
    exposed = Mcp(module.app)
    for capability_id in module.app.capabilities:
        exposed.tool(module.app.capabilities[capability_id])
    exposures = exposed.compile()

    def identity_to_principal(identity: McpAuthenticatedIdentity) -> Principal:
        return Principal(identity.client_id, scopes=identity.scopes)

    authorization = McpAuthorization(exposures, identity_to_principal)
    user = (
        None
        if not scopes
        else AuthenticatedUser(
            AccessToken(token="opaque", client_id="viewer", scopes=sorted(scopes))
        )
    )
    reset = auth_context_var.set(user)
    try:
        visible = authorization.discoverable_tool_names()
    finally:
        auth_context_var.reset(reset)
    return [name for name in authorization.tool_names if name in visible]


@pytest.mark.parametrize("viewer", sorted(VIEWERS))
def test_mcp_discovery_hides_what_the_snapshot_hides_for_the_same_viewer(
    project: Path, viewer: str
) -> None:
    """MCP filters on its own path; agreeing is a property, not a shared line.

    `ScopeVisible` exists because these two must not diverge. If this fails,
    one of the two changed its idea of what a declared scope means, and a
    caller would see a tool through one surface that the other denies knowing.
    """
    scopes = VIEWERS[viewer]

    assert mcp_visible(scopes) == from_model(scopes)
