"""Django async-view conformance evidence for the public host boundary."""

from __future__ import annotations

import asyncio
import json

from django.conf import settings

if not settings.configured:
    settings.configure(SECRET_KEY="fixture", DEFAULT_CHARSET="utf-8", USE_I18N=False)
    import django

    django.setup()

from django.http import HttpResponse
from django.test import AsyncRequestFactory

from tests.conformance.harness import HostFixture, HostHarness
from tests.integration.django.reference_application import DjangoHost, FixtureState


def _body(response: HttpResponse) -> dict[str, object]:
    return json.loads(response.content)


def test_django_async_views_keep_requests_and_orm_outside_agnara() -> None:
    async def run() -> None:
        host = DjangoHost(FixtureState())
        factory = AsyncRequestFactory()
        assert _body(await host.native_view(factory.get("/native"))) == {"native": "django"}
        assert _body(
            await host.echo_view(factory.get("/echo/x", headers={"X-Fixture-Auth": "reader"}), "x")
        ) == {"ok": True, "value": "agnara:x"}
        denied = await host.echo_view(factory.get("/echo/x"), "x")
        assert denied.status_code == 403 and _body(denied)["code"] == "forbidden"
        assert _body(
            await host.compose_view(factory.get("/compose", headers={"X-Fixture-Auth": "reader"}))
        ) == {"ok": True, "value": "composed:agnara:child"}
        headers = {"X-Fixture-Auth": "reader", "X-Fixture-Retry": "fixture-duplicate"}
        assert _body(await host.write_view(factory.post("/write", **headers))) == {
            "ok": True,
            "value": 1,
        }
        assert _body(await host.write_view(factory.post("/write", **headers))) == {
            "ok": True,
            "value": 1,
        }
        assert host.state.effects == 1
        failed = await host.failure_view(
            factory.get("/failure", headers={"X-Fixture-Auth": "reader"})
        )
        assert failed.status_code == 400 and _body(failed)["code"] == "internal_failure"
        assert (await host.orm_boundary_view(factory.get("/orm"))).status_code == 204
        await host.aclose()
        assert host.state.closes == 1

    asyncio.run(run())


class DjangoHarness(HostFixture):
    """Adapt the Django fixture to the shared HostHarness."""

    def call_sync(self, value: object) -> str:
        async def call() -> None:
            host = DjangoHost(FixtureState())
            response = await host.echo_view(
                AsyncRequestFactory().get("/", headers={"X-Fixture-Auth": "reader"}), str(value)
            )
            assert _body(response)["value"] == f"agnara:{value}"
            await host.aclose()

        asyncio.run(call())
        return super().call_sync(value)


def test_django_fixture_uses_shared_host_harness() -> None:
    host = DjangoHarness("django")
    assert (
        HostHarness().run_case(
            host,
            "async-view",
            lambda item: item.call_sync("ok"),
            lambda value: value == "sync:django:ok",
        )
        == "sync:django:ok"
    )


def test_django_adversarial_context_isolation_and_lifecycle_integrity() -> None:
    async def run() -> None:
        host = DjangoHost(FixtureState())
        factory = AsyncRequestFactory()

        # 1. Concurrent authenticated vs unauthenticated/malicious requests
        auth_req = host.echo_view(
            factory.get("/echo/secret-django", headers={"X-Fixture-Auth": "reader"}),
            "secret-django",
        )
        attacker_echo = host.echo_view(
            factory.get("/echo/secret-django", headers={"X-Fixture-Auth": "attacker"}),
            "secret-django",
        )
        attacker_write = host.write_view(
            factory.post(
                "/write",
                headers={"X-Fixture-Auth": "attacker", "X-Fixture-Retry": "fixture-duplicate"},
            )
        )
        auth_write = host.write_view(
            factory.post(
                "/write",
                headers={"X-Fixture-Auth": "reader", "X-Fixture-Retry": "fixture-duplicate"},
            )
        )

        (
            auth_echo_resp,
            attacker_echo_resp,
            attacker_write_resp,
            auth_write_resp,
        ) = await asyncio.gather(auth_req, attacker_echo, attacker_write, auth_write)

        # Authenticated echo succeeds
        assert auth_echo_resp.status_code == 200
        assert _body(auth_echo_resp) == {"ok": True, "value": "agnara:secret-django"}

        # Attacker echo and write fail closed with 403 Forbidden
        assert attacker_echo_resp.status_code == 403
        assert _body(attacker_echo_resp)["code"] == "forbidden"
        assert attacker_write_resp.status_code == 403
        assert _body(attacker_write_resp)["code"] == "forbidden"

        # Authenticated write succeeds
        assert auth_write_resp.status_code == 200
        assert _body(auth_write_resp) == {"ok": True, "value": 1}

        # Side effects strictly bounded to authenticated execution
        assert host.state.effects == 1

        # 2. Verify Django HttpRequest / HttpResponse are NOT bound in the DI container
        assert host.state.container is not None
        from django.http import HttpRequest, HttpResponse

        assert not host.state.container.registry.is_bound(HttpRequest)
        assert not host.state.container.registry.is_bound(HttpResponse)

        # 3. Double-close idempotency on the host: calling aclose multiple times is safe
        await host.aclose()
        await host.aclose()
        assert host.state.closes == 1

    asyncio.run(run())
