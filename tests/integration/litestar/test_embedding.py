"""Litestar owns startup, invocation and shutdown on its lifespan loop."""

from __future__ import annotations

import asyncio

import pytest
from litestar import Request as LitestarRequest
from litestar.testing import TestClient

from agnara.di import DIContainer
from tests.conformance.harness import BrokenHostFixture, HostContractError, HostFixture, HostHarness
from tests.integration.litestar.reference_application import Host, State, create_application


class _LitestarHarnessHost(HostFixture):
    """Adapt the Litestar fixture to the shared HostHarness."""

    host: Host | None = None

    def call_sync(self, value: object) -> str:
        app, host = create_application(State())
        with TestClient(app) as client:
            resp = client.get(f"/agnara/echo/{value}", headers={"x-fixture-auth": "reader"})
            assert resp.status_code == 200
            assert resp.json() == {"ok": True, "value": f"agnara:{value}"}
        self.host = host
        return super().call_sync(value)

    def stop(self) -> None:
        assert self.host is not None
        assert (self.host.state.starts, self.host.state.closes) == (1, 1)
        super().stop()


def test_litestar_fixture_uses_shared_host_harness() -> None:
    host = _LitestarHarnessHost("litestar")
    result = HostHarness().run_case(
        host,
        "direct-runtime",
        lambda fixture: fixture.call_sync("harness"),
        lambda value: value == "sync:litestar:harness",
    )
    assert result == "sync:litestar:harness"
    assert host.events == ["start", "sync", "stop"]


def test_litestar_routes_use_public_runtime_boundary() -> None:
    app, host = create_application(State())
    assert host.state.runtime is None and host.state.container is None
    with TestClient(app) as client:
        assert client.get("/native").json() == {"native": "litestar"}
        assert client.get("/agnara/echo/x", headers={"x-fixture-auth": "reader"}).status_code == 200
        assert client.get("/agnara/echo/x").status_code == 403
        assert (
            client.get("/agnara/compose", headers={"x-fixture-auth": "reader"}).status_code == 200
        )
        headers = {"x-fixture-auth": "reader", "x-fixture-retry": "fixture-duplicate"}
        assert client.post("/agnara/write", headers=headers).status_code == 200
        assert client.post("/agnara/write", headers=headers).status_code == 200
        assert host.state.effects == 1
    assert (host.state.starts, host.state.closes) == (1, 1)
    assert host.state.runtime is None and host.state.container is None


def test_litestar_adversarial_context_isolation_and_lifecycle_integrity() -> None:
    app, host = create_application(State())
    with TestClient(app) as client:
        auth_headers = {"x-fixture-auth": "reader"}
        attacker_headers = {"x-fixture-auth": "attacker", "x-fixture-retry": "fixture-duplicate"}
        # A denied first call must not initialize even the singleton.
        attacker_echo = client.get("/agnara/echo/secret-litestar", headers=attacker_headers)
        attacker_write = client.post("/agnara/write", headers=attacker_headers)
        assert host.state.connections == host.state.sessions == []
        auth_resp = client.get("/agnara/echo/secret-litestar", headers=auth_headers)
        auth_write = client.post(
            "/agnara/write",
            headers={"x-fixture-auth": "reader", "x-fixture-retry": "fixture-duplicate"},
        )
        assert auth_resp.status_code == 200
        assert auth_resp.json() == {"ok": True, "value": "agnara:secret-litestar"}
        assert auth_write.status_code == 200
        assert auth_write.json() == {"ok": True, "value": 1}
        assert attacker_echo.status_code == attacker_write.status_code == 403
        assert attacker_echo.json()["code"] == attacker_write.json()["code"] == "forbidden"
        assert host.state.effects == 1
        assert host.state.container is not None
        assert not host.state.container.registry.is_bound(LitestarRequest)
    assert host.state.closes == 1


def test_litestar_lifespan_owns_container_and_resource_loops(monkeypatch) -> None:
    construction_loops: list[int] = []
    close_loops: list[int] = []
    original_init = DIContainer.__init__
    original_close = DIContainer.aclose

    def record_init(self, registry):
        construction_loops.append(id(asyncio.get_running_loop()))
        original_init(self, registry)

    async def record_close(self):
        close_loops.append(id(asyncio.get_running_loop()))
        await original_close(self)

    monkeypatch.setattr(DIContainer, "__init__", record_init)
    monkeypatch.setattr(DIContainer, "aclose", record_close)
    app, host = create_application(State())
    assert construction_loops == []
    with TestClient(app) as client:
        headers = {"x-fixture-auth": "reader"}
        for value in ("first", "second"):
            assert client.get(f"/agnara/echo/{value}", headers=headers).status_code == 200
        failed = client.get("/agnara/failure", headers=headers)
        assert failed.status_code == 400
        assert failed.json() == {"ok": False, "code": "internal_failure"}
        assert "host exception" not in failed.text
        assert len(host.state.connections) == 1 and not host.state.connections[0].closed
        assert len(host.state.sessions) == 3
        assert len({id(session) for session in host.state.sessions}) == 3
        assert all(session.closed for session in host.state.sessions)
        assert all(
            session.connection is host.state.connections[0] for session in host.state.sessions
        )
    assert host.state.connections[0].closed
    assert len(construction_loops) == len(close_loops) == 1
    assert construction_loops == close_loops
    assert {loop for _, loop in host.state.events} == set(construction_loops)
    assert [name for name, _ in host.state.events] == [
        "startup",
        "connection.open",
        "session.open",
        "echo",
        "session.close",
        "session.open",
        "echo",
        "session.close",
        "session.open",
        "failure",
        "session.close",
        "connection.close",
        "shutdown",
    ]


def test_litestar_exceptional_client_exit_closes_singleton_on_owner_loop() -> None:
    app, host = create_application(State())
    with (
        pytest.raises(RuntimeError, match="test client owner failure"),
        TestClient(app) as client,
    ):
        assert client.get("/agnara/echo/x", headers={"x-fixture-auth": "reader"}).status_code == 200
        raise RuntimeError("test client owner failure")
    assert (host.state.starts, host.state.closes) == (1, 1)
    assert host.state.connections[0].closed and host.state.sessions[0].closed
    assert host.state.runtime is None and host.state.container is None
    assert len({loop for _, loop in host.state.events}) == 1
    assert [name for name, _ in host.state.events][-2:] == ["connection.close", "shutdown"]


def test_shared_harness_rejects_lifecycle_divergence() -> None:
    with pytest.raises(HostContractError):
        HostHarness().run_case(
            BrokenHostFixture("litestar-broken"),
            "lifecycle",
            lambda host: host.call_sync("x"),
            lambda _: True,
        )
