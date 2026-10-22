"""GHSA-84m7-p3x7-pcfv regression at the installed SDK transport boundary.

Legacy initialization is needed to exercise the SDK's stateful transport.
This dependency test does not add legacy protocol support to Agnara's API.
All HTTP exchanges stay in process, with one session and a bounded lifespan.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient, Response
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from agnara_mcp import build_mcp_discovery_server


def server():
    return build_mcp_discovery_server([], name="session-regression", version="test")


@asynccontextmanager
async def host(
    *,
    idle_timeout: float = 30,
) -> AsyncIterator[tuple[StreamableHTTPSessionManager, AsyncClient]]:
    manager = StreamableHTTPSessionManager(
        server(), json_response=True, max_sessions=1, session_idle_timeout=idle_timeout
    )
    async with (
        asyncio.timeout(10),
        manager.run(),
        AsyncClient(
            transport=ASGITransport(app=manager.handle_request),
            base_url="http://localhost",
            headers={"accept": "application/json, text/event-stream"},
        ) as client,
    ):
        yield manager, client
    assert not manager._server_instances


async def initialize(client: AsyncClient, request_id: int = 1) -> Response:
    return await client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "bounded-regression", "version": "test"},
            },
        },
    )


def test_sdk_stateful_session_defaults_are_bounded() -> None:
    manager = StreamableHTTPSessionManager(server())
    assert manager.max_sessions == 10_000
    assert manager.session_idle_timeout == 1800


@pytest.mark.parametrize("payload", [b"{", b'{"jsonrpc":"2.0","id":1,"method":"ping"}'])
def test_refused_opening_requests_do_not_retain_session_state(payload: bytes) -> None:
    async def scenario() -> None:
        manager = StreamableHTTPSessionManager(server(), json_response=True)
        async with (
            asyncio.timeout(10),
            manager.run(),
            AsyncClient(
                transport=ASGITransport(app=manager.handle_request),
                base_url="http://localhost",
                headers={
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                },
            ) as client,
        ):
            for _ in range(3):
                response = await client.post("/", content=payload)
                assert response.status_code == 400
                assert not manager._server_instances
        assert not manager._server_instances

    asyncio.run(scenario())


def test_capacity_preserves_existing_sessions_and_delete_reclaims_the_slot() -> None:
    async def scenario() -> None:
        async with host() as (manager, client):
            malformed = await client.post(
                "/", content=b"{", headers={"content-type": "application/json"}
            )
            assert malformed.status_code == 400
            assert not manager._server_instances

            first = await initialize(client)
            assert first.status_code == 200
            session_id = first.headers["mcp-session-id"]
            assert len(manager._server_instances) == 1
            assert (await initialize(client, 2)).status_code == 503
            assert len(manager._server_instances) == 1

            headers = {"mcp-session-id": session_id, "mcp-protocol-version": "2025-03-26"}
            initialized = await client.post(
                "/", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
            )
            assert initialized.status_code == 202
            ping = await client.post(
                "/", headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "ping"}
            )
            assert ping.status_code == 200
            assert ping.json()["result"] == {}

            assert (await client.delete("/", headers=headers)).status_code == 200
            assert not manager._server_instances
            second = await initialize(client, 4)
            assert second.status_code == 200
            assert second.headers["mcp-session-id"] != session_id

    asyncio.run(scenario())


def test_concurrent_opening_requests_do_not_exceed_the_session_limit() -> None:
    async def scenario() -> None:
        async with host() as (manager, client):
            async with asyncio.TaskGroup() as tasks:
                requests = [tasks.create_task(initialize(client, index)) for index in range(4)]
            assert sorted(request.result().status_code for request in requests) == [
                200,
                503,
                503,
                503,
            ]
            assert len(manager._server_instances) == 1

    asyncio.run(scenario())


def test_idle_expiry_reclaims_the_session_and_rejects_its_old_id() -> None:
    async def scenario() -> None:
        async with host(idle_timeout=0.05) as (manager, client):
            first = await initialize(client)
            assert first.status_code == 200
            session_id = first.headers["mcp-session-id"]
            async with asyncio.timeout(2):
                while manager._server_instances:
                    await asyncio.sleep(0.01)
            expired = await client.post(
                "/",
                headers={"mcp-session-id": session_id, "mcp-protocol-version": "2025-03-26"},
                json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
            )
            assert expired.status_code == 404
            assert (await initialize(client, 3)).status_code == 200

    asyncio.run(scenario())
