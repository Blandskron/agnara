from __future__ import annotations

import asyncio

from litestar.testing import TestClient

from tests.conformance.harness import BrokenHostFixture, HostContractError, HostHarness
from tests.integration.litestar.reference_application import State, create_application


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


def test_shared_harness_rejects_lifecycle_divergence() -> None:
    with __import__("pytest").raises(HostContractError):
        HostHarness().run_case(
            BrokenHostFixture("litestar-broken"),
            "lifecycle",
            lambda host: host.call_sync("x"),
            lambda _: True,
        )
