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


def test_django_fixture_uses_shared_host_harness() -> None:
    class DjangoHarness(HostFixture):
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
