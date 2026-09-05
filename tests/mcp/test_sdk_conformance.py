"""E7.8: bounded modern SDK conformance, not network/protocol certification.

Requests traverse the official ClientSession and modern server dispatcher.
No adapter handler is called directly and no authentication function is mocked.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from importlib.metadata import version

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp_types import INVALID_PARAMS, METHOD_NOT_FOUND, EmptyResult, Request

from agnara import Agnara
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara.policy import Principal
from agnara_mcp import (
    MCP_PROTOCOL_VERSION,
    Mcp,
    McpAuthenticatedIdentity,
    McpAuthorization,
    build_mcp_discovery_server,
    project_mcp_tools,
)
from mcp import Client, MCPError


def run[T](awaitable: Awaitable[T]) -> T:
    async def bounded() -> T:
        async with asyncio.timeout(10):
            return await awaitable

    return asyncio.run(bounded())


def surface():
    app = Agnara("conformance")
    effects: list[str] = []

    @app.capability
    def public(value: int) -> int:
        effects.append("public")
        return value

    @app.capability(scopes={"records:read"})
    def restricted() -> str:
        effects.append("restricted")
        return "private"

    mcp = Mcp(app)
    mcp.tool(public)
    mcp.tool(restricted)
    exposures = mcp.compile()
    plans = [ExecutionPlan.compile(app.capabilities[key], DIRegistry()) for key in app.capabilities]

    def identity_to_principal(identity: McpAuthenticatedIdentity) -> Principal:
        return Principal(identity.client_id, scopes=identity.scopes)

    server = build_mcp_discovery_server(
        project_mcp_tools(exposures, plans),
        name="conformance",
        version="test",
        authorization=McpAuthorization(exposures, identity_to_principal),
    )
    return server, effects


def test_modern_discovery_contract_survives_the_official_client_validator() -> None:
    assert version("mcp") == "2.1.1"
    assert version("mcp-types") == "2.1.1"
    server, effects = surface()

    async def scenario() -> None:
        async with Client(server, mode="auto") as client:
            assert client.protocol_version == MCP_PROTOCOL_VERSION == "2026-07-28"
            discovery = client.session.discover_result
            assert discovery is not None
            assert discovery.supported_versions == [MCP_PROTOCOL_VERSION]
            assert discovery.capabilities.model_dump(by_alias=True, exclude_none=True) == {
                "tools": {"listChanged": False}
            }
            assert discovery.ttl_ms == 0
            assert discovery.cache_scope == "private"
            result = await client.list_tools()
            assert result.next_cursor is None
            assert result.ttl_ms == 0
            assert result.cache_scope == "private"
            assert [tool.name for tool in result.tools] == ["conformance.public"]
            assert result.tools[0].input_schema == {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            }
            assert result.tools[0].output_schema is None
            assert result.tools[0].execution is None

    run(scenario())
    assert effects == []


@pytest.mark.parametrize("cursor", ["", "not-issued", 42, ["invalid"]])
def test_invalid_pagination_is_a_protocol_error_and_connection_recovers(cursor: object) -> None:
    server, effects = surface()

    async def scenario() -> None:
        async with Client(server, mode="auto") as client:
            # Generic official Request deliberately bypasses the typed pagination
            # constructor, so malformed data reaches server-side validation.
            request = Request[dict[str, object], str](
                method="tools/list", params={"cursor": cursor}
            )
            with pytest.raises(MCPError) as captured:
                await client.session.send_request(request, EmptyResult)
            assert captured.value.code == INVALID_PARAMS
            assert [item.name for item in (await client.list_tools()).tools] == [
                "conformance.public"
            ]

    run(scenario())
    assert effects == []


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("tools/call", {"name": "conformance.public", "arguments": {"value": 1}}),
        ("tools/call", {"name": "conformance.restricted", "arguments": {}}),
        (
            "tools/call",
            {
                "name": "conformance.restricted",
                "arguments": {},
                "requestState": "forged-state",
                "inputResponses": {
                    "confirmation": {"action": "accept", "content": {"confirmed": True}}
                },
            },
        ),
        ("resources/list", {}),
        ("prompts/list", {}),
        ("tasks/list", {}),
        ("tasks/get", {"taskId": "unissued"}),
    ],
)
def test_unsupported_methods_fail_without_effects(method: str, params: dict[str, object]) -> None:
    server, effects = surface()

    async def scenario() -> None:
        async with Client(server, mode="auto") as client:
            with pytest.raises(MCPError) as captured:
                await client.session.send_request(
                    Request[dict[str, object], str](method=method, params=params), EmptyResult
                )
            assert captured.value.code == METHOD_NOT_FOUND
            assert [tool.name for tool in (await client.list_tools()).tools] == [
                "conformance.public"
            ]

    run(scenario())
    assert effects == []


def test_concurrent_request_identities_do_not_leak_or_reuse_private_cached_lists() -> None:
    server, effects = surface()

    async def scenario() -> None:
        async with Client(server, mode="auto") as client:
            barrier = asyncio.Barrier(3)

            async def inspect(scopes: list[str] | None) -> None:
                # This is the SDK's verified identity context, not a test of
                # OAuth verification. Each task owns/reset its ContextVar token.
                user = (
                    None
                    if scopes is None
                    else AuthenticatedUser(
                        AccessToken(token="secret-token", client_id="client", scopes=scopes)
                    )
                )
                context_token = auth_context_var.set(user)
                try:
                    for _ in range(3):
                        await barrier.wait()
                        result = await client.list_tools()
                        expected = ["conformance.public"]
                        if scopes:
                            expected.append("conformance.restricted")
                        assert [tool.name for tool in result.tools] == expected
                        assert result.ttl_ms == 0
                        assert result.cache_scope == "private"
                        assert "secret-token" not in result.model_dump_json()
                        result.tools[0].input_schema["secret-marker"] = True
                        # The next response must not inherit this client's mutation.
                        again = await client.list_tools()
                        assert "secret-marker" not in json.dumps(again.tools[0].input_schema)
                finally:
                    auth_context_var.reset(context_token)

            async with asyncio.TaskGroup() as tasks:
                for scopes in (None, [], ["records:read"]):
                    tasks.create_task(inspect(scopes))
            # After authenticated calls on this same client, anonymous discovery
            # must still exclude the restricted capability.
            assert [tool.name for tool in (await client.list_tools()).tools] == [
                "conformance.public"
            ]

    run(scenario())
    assert effects == []
