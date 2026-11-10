"""The application-owned recipe preserves the shipped adapter's default."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from examples.a2a_disconnect import cancel_on_disconnect

from tests.a2a.test_a2a_network import HEADERS, category, envelope, official, raw_client, serve


def run(awaitable):
    async def bounded():
        before = asyncio.all_tasks()
        async with asyncio.timeout(10):
            result = await awaitable
        assert asyncio.all_tasks() == before, "recipe left an owned task alive"
        return result

    return asyncio.run(bounded())


async def no_send(message):
    raise AssertionError(f"unexpected response: {message['type']}")


def test_refusal_before_first_receive_does_not_start_a_body_reader() -> None:
    async def scenario():
        sent = []

        async def receive():
            raise AssertionError("authentication refusal read a body")

        async def send(message):
            sent.append(message)

        async def application(scope, receive, send):
            await asyncio.sleep(0)
            await send({"type": "http.response.start", "status": 401})
            await send({"type": "http.response.body", "body": b""})

        await cancel_on_disconnect(application)({"type": "http", "method": "POST"}, receive, send)
        assert [m["type"] for m in sent] == ["http.response.start", "http.response.body"]
        assert sent[0]["status"] == 401

    run(scenario())


@pytest.mark.parametrize("scope", [{"type": "lifespan"}, {"type": "http", "method": "GET"}])
def test_non_post_traffic_bypasses_the_policy(scope) -> None:
    async def scenario():
        seen = []

        async def receive():
            return {"type": "fixture.event"}

        async def application(actual, actual_receive, actual_send):
            assert actual is scope and actual_receive is receive and actual_send is no_send
            seen.append(await actual_receive())

        await cancel_on_disconnect(application)(scope, receive, no_send)
        assert seen == [{"type": "fixture.event"}]

    run(scenario())


def test_body_events_are_identical_ordered_and_prefetch_is_bounded() -> None:
    async def scenario():
        messages = [
            {"type": "http.request", "body": b"one", "more_body": True},
            {"type": "http.request", "body": b"two", "more_body": True},
            {"type": "http.request", "body": b"three", "more_body": False},
        ]
        reads = 0
        first = asyncio.Event()
        release = asyncio.Event()
        seen = []
        active = 0

        async def receive():
            nonlocal reads, active
            active += 1
            assert active == 1, "multiple owners read the underlying stream"
            try:
                index = reads
                reads += 1
                if index < len(messages):
                    return messages[index]
                await asyncio.Event().wait()
                raise AssertionError("unreachable")
            finally:
                active -= 1

        async def application(scope, receive, send):
            seen.append(await receive())
            first.set()
            await release.wait()
            seen.append(await receive())
            seen.append(await receive())

        async with asyncio.TaskGroup() as owned:
            work = owned.create_task(
                cancel_on_disconnect(application)(
                    {"type": "http", "method": "POST"}, receive, no_send
                )
            )
            await first.wait()
            # Let the pump fill its single event slot without consuming more.
            for _ in range(3):
                await asyncio.sleep(0)
            assert reads == 2
            release.set()
        assert work.result() is None and active == 0
        assert len(seen) == 3 and all(a is b for a, b in zip(seen, messages, strict=True))

    run(scenario())


@pytest.mark.parametrize("source", ["application", "receive", "send"])
def test_errors_propagate_and_owned_work_is_joined(source: str) -> None:
    async def scenario():
        closed = []

        async def receive():
            if source == "receive":
                raise ValueError("receive failed")
            await asyncio.Event().wait()

        async def send(message):
            raise ValueError("send failed")

        async def application(scope, receive, send):
            try:
                if source == "application":
                    raise ValueError("application failed")
                if source == "send":
                    await send({"type": "http.response.body"})
                await receive()
            finally:
                closed.append("application.close")

        with pytest.raises(ExceptionGroup) as caught:
            await cancel_on_disconnect(application)(
                {"type": "http", "method": "POST"}, receive, send
            )
        assert any(
            isinstance(e, ValueError) and str(e) == f"{source} failed"
            for e in caught.value.exceptions
        )
        assert closed == ["application.close"]

    run(scenario())


@pytest.mark.parametrize("disconnect_race", [False, True])
def test_external_cancellation_is_never_suppressed(disconnect_race: bool) -> None:
    async def scenario():
        incoming = asyncio.Queue()
        await incoming.put({"type": "http.request", "body": b"{}", "more_body": False})
        entered = asyncio.Event()
        cleanup_entered = asyncio.Event()
        closed = []

        async def application(scope, receive, send):
            try:
                await receive()
                entered.set()
                await asyncio.Event().wait()
            finally:
                try:
                    cleanup_entered.set()
                    if disconnect_race:
                        await asyncio.Event().wait()
                finally:
                    closed.append("application.close")

        async with asyncio.TaskGroup() as owned:
            work = owned.create_task(
                cancel_on_disconnect(application)(
                    {"type": "http", "method": "POST"}, incoming.get, no_send
                )
            )
            await entered.wait()
            if disconnect_race:
                incoming.put_nowait({"type": "http.disconnect"})
                # The policy has already cancelled its request and is joining
                # cleanup. External cancellation must still leave the owner.
                await cleanup_entered.wait()
            work.cancel()
        assert work.cancelled() and closed == ["application.close"]

    run(scenario())


def test_completed_response_prevents_late_disconnect_from_cancelling_cleanup() -> None:
    async def scenario():
        sent = asyncio.Event()
        eof = asyncio.Event()
        release = asyncio.Event()
        closed = []
        reads = 0

        async def receive():
            nonlocal reads
            reads += 1
            if reads == 1:
                return {"type": "http.request", "body": b"{}", "more_body": False}
            await sent.wait()
            eof.set()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body":
                sent.set()

        async def application(scope, receive, send):
            await receive()
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"done"})
            try:
                await release.wait()
            except asyncio.CancelledError:
                raise AssertionError(
                    "late disconnect cancelled completed-response cleanup"
                ) from None
            closed.append("application.close")

        async with asyncio.TaskGroup() as owned:
            work = owned.create_task(
                cancel_on_disconnect(application)({"type": "http", "method": "POST"}, receive, send)
            )
            await eof.wait()
            # Allow pump completion and its owner's wait callback to run.
            for _ in range(3):
                await asyncio.sleep(0)
            release.set()
        assert work.result() is None and closed == ["application.close"]

    run(scenario())


@pytest.mark.parametrize("stage", ["mid_body", "handler"])
def test_opt_in_recipe_cancels_real_disconnected_request(stage: str) -> None:
    async def scenario():
        # Deadline is intentionally beyond the fixture's outer 15s bound.
        # Passing therefore requires peer cancellation, not deadline cleanup.
        async with serve(timeout=30, wrap=cancel_on_disconnect) as (url, state, _):
            body = b"{" if stage == "mid_body" else json.dumps(envelope(-1)).encode()
            _, writer = await raw_client(url, body, 1000 if stage == "mid_body" else len(body))
            try:
                await (state.body_received if stage == "mid_body" else state.entered).wait()
            finally:
                writer.close()
                await writer.wait_closed()
            await state.request_closed.wait()
            assert state.active == 0 and state.outcomes == []
            if stage == "mid_body":
                assert state.effects == []
            else:
                assert state.effects == [
                    "pool.open",
                    "ledger.open",
                    "handler.enter",
                    "handler.cancel",
                    "handler.close",
                    "ledger.close",
                ]
            async with httpx.AsyncClient(base_url=url, headers=HEADERS, trust_env=False) as http:
                assert await official(http, url, 4) == 8
        assert state.effects[-1] == "pool.close"

    run(scenario())


def test_opt_in_host_preserves_real_authentication_and_policy_refusals() -> None:
    async def scenario():
        async with serve(timeout=30, wrap=cancel_on_disconnect) as (url, state, _):
            async with httpx.AsyncClient(base_url=url, headers=HEADERS, trust_env=False) as http:
                refusal = await http.post("/", content=b"{", headers={"Authorization": "unknown"})
                assert refusal.status_code == 401 and not state.body_received.is_set()
                invalid = await http.post("/", json=envelope("bad"))
                assert category(invalid.json()) == "invalid_input"
                denied = await http.post(
                    "/", json=envelope(3), headers={"Authorization": "Bearer fixture-unscoped"}
                )
                assert category(denied.json()) == "forbidden" and state.effects == []
                assert await official(http, url, 3) == 6
                assert state.principals == ["reader"]
                assert state.metadata == [{"transport": "a2a"}]
            assert http.is_closed
        assert "handler.cancel" not in state.effects
        assert state.effects[-1] == "pool.close"

    run(scenario())
