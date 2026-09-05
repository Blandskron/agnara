"""E7.8: bounded modern SDK conformance, not network/protocol certification.

Requests traverse the official ClientSession and modern server dispatcher.
No adapter handler is called directly and no authentication function is mocked.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from importlib.metadata import version
from typing import Any

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp_types import (
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    REQUEST_TIMEOUT,
    CallToolResult,
    EmptyResult,
    Request,
    TextContent,
)

from agnara import Agnara
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import ExecutionPlan
from agnara.policy import Principal
from agnara_mcp import (
    MCP_PROTOCOL_VERSION,
    Mcp,
    McpAuthenticatedIdentity,
    McpAuthorization,
    build_mcp_discovery_server,
    build_mcp_server,
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


def text(result: CallToolResult) -> Any:
    """Read the single text block a projected tool result always carries."""
    assert len(result.content) == 1
    block = result.content[0]
    assert isinstance(block, TextContent)
    return json.loads(block.text)


def invocable_surface(*, timeout: float | None = None):
    """The same projection as ``surface``, wired to serve ``tools/call`` too."""
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

    @app.capability
    async def slow() -> str:
        effects.append("slow:start")
        try:
            await asyncio.sleep(30)
        finally:
            effects.append("slow:unwound")
        return "never"

    mcp = Mcp(app)
    mcp.tool(public)
    mcp.tool(restricted)
    mcp.tool(slow)
    exposures = mcp.compile()
    registry = DIRegistry()
    plans = [ExecutionPlan.compile(app.capabilities[key], registry) for key in app.capabilities]

    def identity_to_principal(identity: McpAuthenticatedIdentity) -> Principal:
        return Principal(identity.client_id, scopes=identity.scopes)

    server = build_mcp_server(
        exposures,
        plans,
        DIContainer(registry),
        name="conformance",
        version="test",
        authorization=McpAuthorization(exposures, identity_to_principal),
        timeout=timeout,
    )
    return server, effects


def test_a_tool_call_traverses_the_official_client_and_returns_a_validated_result() -> None:
    server, effects = invocable_surface()

    async def scenario() -> None:
        async with Client(server, mode="auto") as client:
            assert client.protocol_version == MCP_PROTOCOL_VERSION
            discovery = client.session.discover_result
            assert discovery is not None
            # Serving invocation must not start advertising another surface.
            assert discovery.capabilities.model_dump(by_alias=True, exclude_none=True) == {
                "tools": {"listChanged": False}
            }
            result = await client.call_tool("conformance.public", {"value": 41})
            assert result.is_error is False
            assert result.structured_content == {"result": 41}
            assert text(result) == {"result": 41}
            invalid = await client.call_tool("conformance.public", {"value": "not an integer"})
            assert invalid.is_error is True
            assert text(invalid)["code"] == "invalid_input"

    run(scenario())
    assert effects == ["public"]


def test_invocation_authorization_matches_discovery_for_the_same_identity() -> None:
    server, effects = invocable_surface()

    async def scenario() -> None:
        async with Client(server, mode="auto") as client:
            denied = await client.call_tool("conformance.restricted", {})
            assert denied.is_error is True
            assert text(denied)["code"] == "forbidden"
            assert [tool.name for tool in (await client.list_tools()).tools] == [
                "conformance.public",
                "conformance.slow",
            ]

            context_token = auth_context_var.set(
                AuthenticatedUser(
                    AccessToken(token="secret-token", client_id="agent", scopes=["records:read"])
                )
            )
            try:
                granted = await client.call_tool("conformance.restricted", {})
            finally:
                auth_context_var.reset(context_token)
            assert granted.is_error is False
            assert granted.structured_content == {"result": "private"}
            assert "secret-token" not in granted.model_dump_json()

    run(scenario())
    assert effects == ["restricted"]


@pytest.mark.parametrize(
    "params",
    [
        {"name": "conformance.absent", "arguments": {}},
        {"name": "conformance.public", "arguments": {"value": 1}, "task": {"ttl": 1000}},
        {
            "name": "conformance.public",
            "arguments": {"value": 1},
            "requestState": "forged-state",
            "inputResponses": {
                "confirmation": {"action": "accept", "content": {"confirmed": True}}
            },
        },
    ],
)
def test_unknown_task_augmented_and_forged_resumption_calls_are_protocol_errors(
    params: dict[str, object],
) -> None:
    server, effects = invocable_surface()

    async def scenario() -> None:
        async with Client(server, mode="auto") as client:
            with pytest.raises(MCPError) as captured:
                await client.session.send_request(
                    Request[dict[str, object], str](method="tools/call", params=params),
                    EmptyResult,
                )
            assert captured.value.code == INVALID_PARAMS
            # The connection still serves the surfaces it does implement.
            assert (await client.call_tool("conformance.public", {"value": 1})).is_error is False

    run(scenario())
    assert effects == ["public"]


def test_a_server_deadline_ends_an_invocation_as_a_canonical_tool_error() -> None:
    server, effects = invocable_surface(timeout=0.05)

    async def scenario() -> None:
        async with Client(server, mode="auto") as client:
            result = await client.call_tool("conformance.slow", {})
            assert result.is_error is True
            assert text(result)["code"] == "timeout"

    run(scenario())
    assert effects == ["slow:start", "slow:unwound"]


def test_client_abandonment_unwinds_the_invocation_without_answering_it() -> None:
    server, effects = invocable_surface()

    async def scenario() -> None:
        async with Client(server, mode="auto") as client:
            with pytest.raises(MCPError) as captured:
                await client.call_tool("conformance.slow", {}, read_timeout_seconds=0.05)
            assert captured.value.code == REQUEST_TIMEOUT
            # The connection is still usable for a call the server can answer.
            assert (await client.call_tool("conformance.public", {"value": 1})).is_error is False

    run(scenario())
    assert effects[0] == "slow:start"
    assert "slow:unwound" in effects
    assert "public" in effects
