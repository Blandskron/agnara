"""E7.5 MCP authentication-to-principal authorization bridge."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import FrozenInstanceError

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp_types import INTERNAL_ERROR, Tool

from agnara import Agnara
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara.policy import AnonymousPrincipal, Principal
from agnara_mcp import (
    Mcp,
    McpAuthenticatedIdentity,
    McpAuthorization,
    McpAuthorizationDefinitionError,
    project_mcp_tools,
)
from agnara_mcp import build_mcp_discovery_server as build_server
from mcp import Client, MCPError


def run[T](awaitable: Awaitable[T]) -> T:
    return asyncio.run(awaitable)


def token(
    client_id: str,
    *,
    scopes: list[str] | None = None,
    subject: str | None = None,
) -> AccessToken:
    return AccessToken(
        token=f"secret-{client_id}",
        client_id=client_id,
        scopes=scopes or [],
        resource="https://mcp.example.test",
        subject=subject,
        claims={"iss": "https://issuer.example.test", "private": f"claim-{client_id}"},
    )


def tool_surface():
    app = Agnara("records")

    @app.capability
    def public() -> str:
        return "public"

    @app.capability(scopes={"records:read"})
    def read() -> str:
        return "read"

    @app.capability(scopes={"records:admin"})
    def admin() -> str:
        return "admin"

    mcp = Mcp(app)
    mcp.tool(public)
    mcp.tool(read)
    mcp.tool(admin)
    exposures = mcp.compile()
    plans = [
        ExecutionPlan.compile(app.capabilities[capability_id], DIRegistry())
        for capability_id in app.capabilities
    ]
    return exposures, project_mcp_tools(exposures, plans)


def restricted_tool_surface():
    app = Agnara("restricted")

    @app.capability(scopes={"records:admin"})
    def admin() -> str:
        return "admin"

    mcp = Mcp(app)
    mcp.tool(admin)
    exposures = mcp.compile()
    plan = ExecutionPlan.compile(app.capabilities["restricted.admin"], DIRegistry())
    return exposures, project_mcp_tools(exposures, [plan])


def map_principal(identity: McpAuthenticatedIdentity) -> Principal:
    actor = identity.client_id
    if identity.subject is not None:
        actor = f"{actor} acting-for {identity.subject}"
    return Principal(actor, scopes=identity.scopes)


def test_mapper_receives_only_immutable_sanitized_identity() -> None:
    exposures, _ = tool_surface()
    captured: list[McpAuthenticatedIdentity] = []

    def mapper(identity: McpAuthenticatedIdentity) -> Principal:
        captured.append(identity)
        return map_principal(identity)

    authorization = McpAuthorization(exposures, mapper)
    raw = token("desktop-client", scopes=["records:read"], subject="user-123")
    context_token = auth_context_var.set(AuthenticatedUser(raw))
    try:
        principal = authorization.principal()
    finally:
        auth_context_var.reset(context_token)

    assert principal.identity == "desktop-client acting-for user-123"
    assert principal.scopes == frozenset({"records:read"})
    assert captured == [
        McpAuthenticatedIdentity(
            client_id="desktop-client",
            issuer="https://issuer.example.test",
            subject="user-123",
            resource="https://mcp.example.test",
            scopes=frozenset({"records:read"}),
        )
    ]
    identity = captured[0]
    assert not hasattr(identity, "token")
    assert not hasattr(identity, "claims")
    assert "secret-desktop-client" not in repr(identity)
    assert "claim-desktop-client" not in repr(identity)
    with pytest.raises(FrozenInstanceError):
        identity.client_id = "mutated"  # ty: ignore[invalid-assignment]


def test_missing_authentication_is_anonymous_and_never_calls_mapper() -> None:
    exposures, _ = tool_surface()

    def mapper(_identity: McpAuthenticatedIdentity) -> Principal:
        raise AssertionError("anonymous requests must not invoke the mapper")

    principal = McpAuthorization(exposures, mapper).principal()
    assert isinstance(principal, AnonymousPrincipal)
    assert principal.metadata == {"transport": "mcp"}
    assert principal.scopes == frozenset()


def test_discovery_filters_static_scopes_in_declaration_order(monkeypatch) -> None:
    exposures, projected = tool_surface()
    authorization = McpAuthorization(exposures, map_principal)
    monkeypatch.setattr(
        "agnara_mcp.authorization.get_access_token",
        lambda: token("client", scopes=["records:read"]),
    )
    server = build_server(
        projected,
        name="records",
        version="1.0.0",
        authorization=authorization,
    )

    async def inspect() -> None:
        async with Client(server, mode="auto", raise_exceptions=True) as client:
            result = await client.list_tools(cache_mode="bypass")
            assert [item.name for item in result.tools] == ["records.public", "records.read"]
            assert result.cache_scope == "private"
            assert result.ttl_ms == 0

    run(inspect())


def test_anonymous_discovery_exposes_only_scope_free_tools() -> None:
    exposures, projected = tool_surface()
    authorization = McpAuthorization(exposures, map_principal)
    server = build_server(
        projected,
        name="records",
        version="1.0.0",
        authorization=authorization,
    )

    async def inspect() -> None:
        async with Client(server, mode="auto", raise_exceptions=True) as client:
            result = await client.list_tools(cache_mode="bypass")
            assert [item.name for item in result.tools] == ["records.public"]

    run(inspect())


def test_discovery_accepts_an_empty_authorized_result() -> None:
    exposures, projected = restricted_tool_surface()
    server = build_server(
        projected,
        name="restricted",
        version="1.0.0",
        authorization=McpAuthorization(exposures, map_principal),
    )

    async def inspect() -> None:
        async with Client(server, mode="auto", raise_exceptions=True) as client:
            result = await client.list_tools(cache_mode="bypass")
            assert result.tools == []
            assert result.cache_scope == "private"
            assert result.ttl_ms == 0

    run(inspect())


@pytest.mark.parametrize(
    "projected",
    [
        (),
        (Tool(name="records.read", input_schema={"type": "object"}),),
        (
            Tool(name="records.read", input_schema={"type": "object"}),
            Tool(name="records.public", input_schema={"type": "object"}),
            Tool(name="records.admin", input_schema={"type": "object"}),
        ),
    ],
)
def test_authorization_and_projected_tools_must_match_exactly(projected) -> None:
    exposures, _ = tool_surface()
    authorization = McpAuthorization(exposures, map_principal)
    with pytest.raises(McpAuthorizationDefinitionError, match="exactly match"):
        build_server(
            projected,
            name="records",
            version="1.0.0",
            authorization=authorization,
        )


@pytest.mark.parametrize("mapped", [None, AnonymousPrincipal(), object()])
def test_invalid_authenticated_mapper_output_fails_closed(monkeypatch, mapped: object) -> None:
    exposures, _ = tool_surface()
    monkeypatch.setattr(
        "agnara_mcp.authorization.get_access_token",
        lambda: token("client", scopes=["records:read"]),
    )
    authorization = McpAuthorization(exposures, lambda _identity: mapped)  # ty: ignore[invalid-argument-type]
    with pytest.raises(MCPError) as captured:
        authorization.principal()
    assert captured.value.code == INTERNAL_ERROR
    assert captured.value.message == "MCP authorization failed"


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("credential database secret"),
        MCPError(code=-32001, message="authorization provider secret"),
    ],
)
def test_mapper_exception_is_redacted(monkeypatch, error: Exception) -> None:
    exposures, _ = tool_surface()
    monkeypatch.setattr(
        "agnara_mcp.authorization.get_access_token",
        lambda: token("client", scopes=["records:read"]),
    )

    def mapper(_identity: McpAuthenticatedIdentity) -> Principal:
        raise error

    with pytest.raises(MCPError) as captured:
        McpAuthorization(exposures, mapper).principal()
    assert captured.value.code == INTERNAL_ERROR
    assert captured.value.message == "MCP authorization failed"
    assert "secret" not in str(captured.value)


def test_authenticated_identity_rejects_invalid_public_construction() -> None:
    with pytest.raises(McpAuthorizationDefinitionError, match="client_id"):
        McpAuthenticatedIdentity(1, None, None, None, frozenset())  # ty: ignore[invalid-argument-type]
    with pytest.raises(McpAuthorizationDefinitionError, match="frozenset"):
        McpAuthenticatedIdentity(
            "client",
            None,
            None,
            None,
            {"records:read"},  # ty: ignore[invalid-argument-type]
        )


def test_request_contexts_do_not_share_principals() -> None:
    exposures, _ = tool_surface()
    authorization = McpAuthorization(exposures, map_principal)

    async def resolve(client_id: str) -> str:
        context_token = auth_context_var.set(AuthenticatedUser(token(client_id)))
        try:
            await asyncio.sleep(0)
            return authorization.principal().identity
        finally:
            auth_context_var.reset(context_token)

    async def inspect() -> tuple[str, str]:
        first, second = await asyncio.gather(resolve("first"), resolve("second"))
        return first, second

    assert run(inspect()) == ("first", "second")
    assert isinstance(authorization.principal(), AnonymousPrincipal)


def test_authorization_configuration_is_validated() -> None:
    exposures, _ = tool_surface()
    with pytest.raises(TypeError, match="FrozenMcpTools"):
        McpAuthorization(object(), map_principal)  # ty: ignore[invalid-argument-type]
    with pytest.raises(McpAuthorizationDefinitionError, match="callable"):
        McpAuthorization(exposures, object())  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError, match="McpAuthorization or None"):
        build_server([], name="records", version="1.0.0", authorization=object())  # ty: ignore[invalid-argument-type]
