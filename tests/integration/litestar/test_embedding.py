from __future__ import annotations

import asyncio

from litestar.testing import TestClient

from tests.conformance.harness import BrokenHostFixture, HostContractError, HostFixture, HostHarness
from tests.integration.litestar.reference_application import Host, State, create_application


class _LitestarHarnessHost(HostFixture):
    """Adapt the Litestar fixture to the shared HostHarness."""

    host: Host | None = None

    def call_sync(self, value: object) -> str:
        async def run() -> None:
            app, host = create_application(State())
            with TestClient(app) as client:
                resp = client.get(f"/agnara/echo/{value}", headers={"x-fixture-auth": "reader"})
                assert resp.status_code == 200
                assert resp.json() == {"ok": True, "value": f"agnara:{value}"}
            await host.close()
            self.host = host

        asyncio.run(run())
        return super().call_sync(value)

    def stop(self) -> None:
        assert self.host is not None
        assert self.host.state.closes == 1
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
    async def run() -> None:
        app, host = create_application(State())
        with TestClient(app) as client:
            assert client.get("/native").json() == {"native": "litestar"}
            assert (
                client.get("/agnara/echo/x", headers={"x-fixture-auth": "reader"}).status_code
                == 200
            )
            assert client.get("/agnara/echo/x").status_code == 403
            assert (
                client.get("/agnara/compose", headers={"x-fixture-auth": "reader"}).status_code
                == 200
            )
            headers = {"x-fixture-auth": "reader", "x-fixture-retry": "fixture-duplicate"}
            assert client.post("/agnara/write", headers=headers).status_code == 200
            assert client.post("/agnara/write", headers=headers).status_code == 200
            assert host.state.effects == 1
        await host.close()
        assert host.state.closes == 1

    asyncio.run(run())


def test_litestar_adversarial_context_isolation_and_lifecycle_integrity() -> None:
    async def run() -> None:
        app, host = create_application(State())
        with TestClient(app) as client:
            # 1. Authenticated reader vs untrusted attacker
            auth_headers = {"x-fixture-auth": "reader"}
            attacker_headers = {
                "x-fixture-auth": "attacker",
                "x-fixture-retry": "fixture-duplicate",
            }

            auth_resp = client.get("/agnara/echo/secret-litestar", headers=auth_headers)
            attacker_echo = client.get("/agnara/echo/secret-litestar", headers=attacker_headers)
            attacker_write = client.post("/agnara/write", headers=attacker_headers)
            auth_write = client.post(
                "/agnara/write",
                headers={"x-fixture-auth": "reader", "x-fixture-retry": "fixture-duplicate"},
            )

            # Authenticated requests succeed
            assert auth_resp.status_code == 200
            assert auth_resp.json() == {"ok": True, "value": "agnara:secret-litestar"}
            assert auth_write.status_code == 200
            assert auth_write.json() == {"ok": True, "value": 1}

            # Attacker requests fail closed with 403
            assert attacker_echo.status_code == 403
            assert attacker_echo.json()["code"] == "forbidden"
            assert attacker_write.status_code == 403
            assert attacker_write.json()["code"] == "forbidden"

            # Effects strictly bounded
            assert host.state.effects == 1

            # 2. Verify Litestar Request / Response are NOT bound in DI container
            assert host.state.container is not None
            from litestar import Request as LitestarRequest

            assert not host.state.container.registry.is_bound(LitestarRequest)

            # 3. Double-close idempotency
            await host.close()
            await host.close()
            assert host.state.closes == 1

    asyncio.run(run())


def test_shared_harness_rejects_lifecycle_divergence() -> None:
    with __import__("pytest").raises(HostContractError):
        HostHarness().run_case(
            BrokenHostFixture("litestar-broken"),
            "lifecycle",
            lambda host: host.call_sync("x"),
            lambda _: True,
        )
