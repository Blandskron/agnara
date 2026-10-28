"""The HTTP tutorial owns its application resources on one event loop."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from examples import http_service as example

from agnara.di import DIRegistry, Scope, provider


def tracked_application():
    events: list[tuple[str, asyncio.AbstractEventLoop]] = []
    ledgers: list[example.Ledger] = []

    @provider(scope=Scope.SINGLETON)
    async def provide() -> AsyncIterator[example.Ledger]:
        ledger = example.Ledger()
        ledgers.append(ledger)
        owner = asyncio.get_running_loop()
        events.append(("open", owner))
        try:
            yield ledger
        finally:
            ledger.close()
            events.append(("close", asyncio.get_running_loop()))

    dependencies = DIRegistry()
    dependencies.bind(example.Ledger, provide)
    return example.create_application(dependencies), events, ledgers


def test_requests_share_a_singleton_and_reject_bad_input_before_effects() -> None:
    async def run():
        application, events, ledgers = tracked_application()
        async with example.lifespan(application):
            assert events == []
            status, body = await example.request(
                application,
                "PUT",
                "/orders/B-2",
                body=b'{"sku":"gadget","quantity":"bad"}',
                headers=((b"content-type", b"application/json"),),
            )
            assert status == 400 and json.loads(body)["code"] == "invalid_input"
            assert events == [] and ledgers == []
            status, body = await example.request(application, "GET", "/orders/B-2")
            assert (status, json.loads(body)) == (200, {"found": False})
            assert len(ledgers) == 1 and not ledgers[0].closed
            status, body = await example.request(
                application,
                "PUT",
                "/orders/B-2",
                body=b'{"sku":"gadget","quantity":1}',
                headers=((b"content-type", b"application/json"),),
            )
            assert (status, json.loads(body)) == (200, {"stored": "B-2"})
            status, body = await example.request(application, "GET", "/orders/B-2")
            assert (status, json.loads(body)) == (
                200,
                {"found": True, "order": {"sku": "gadget", "quantity": 1}},
            )
            status, body = await example.request(application, "GET", "/openapi.json")
            assert status == 200
            assert set(json.loads(body)["paths"]) == {
                "/orders/{order_id}",
                "/orders/{order_id}/attachments",
            }
            assert await example.request(application, "GET", "/health") == (200, b'"ok"')
            assert len(ledgers) == 1
        assert ledgers[0].closed
        assert events == [
            ("open", asyncio.get_running_loop()),
            ("close", asyncio.get_running_loop()),
        ]
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())


def test_exception_in_demo_host_still_closes_singleton_and_joins_lifespan() -> None:
    async def run():
        application, events, ledgers = tracked_application()
        with pytest.raises(ExceptionGroup) as caught:
            async with example.lifespan(application):
                assert (await example.request(application, "GET", "/orders/A-1"))[0] == 200
                raise RuntimeError("host stopped")
        assert len(caught.value.exceptions) == 1
        assert str(caught.value.exceptions[0]) == "host stopped"
        assert ledgers[0].closed
        assert events == [
            ("open", asyncio.get_running_loop()),
            ("close", asyncio.get_running_loop()),
        ]
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())


def test_cancelled_demo_host_closes_resources_before_cancellation_propagates() -> None:
    async def run():
        application, events, ledgers = tracked_application()
        entered = asyncio.Event()

        async def serve():
            async with example.lifespan(application):
                await example.request(application, "GET", "/orders/A-1")
                entered.set()
                await asyncio.Event().wait()

        async with asyncio.timeout(5), asyncio.TaskGroup() as owned:
            task = owned.create_task(serve())
            await entered.wait()
            task.cancel()
        assert task.cancelled()
        assert ledgers[0].closed
        assert events == [
            ("open", asyncio.get_running_loop()),
            ("close", asyncio.get_running_loop()),
        ]
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())


def test_demonstration_can_repeat_with_fresh_resources(monkeypatch, capsys) -> None:
    closed: list[example.Ledger] = []
    close = example.Ledger.close

    def record_close(self):
        close(self)
        closed.append(self)

    monkeypatch.setattr(example.Ledger, "close", record_close)
    for _ in range(2):
        asyncio.run(example.demonstrate())
    assert len(closed) == 2 and closed[0] is not closed[1]
    assert all(ledger.closed for ledger in closed)
    output = capsys.readouterr().out
    assert output.count("health   -> 200 documented=False") == 2
    assert output.count("oversize -> 413 content_too_large") == 2
