"""WS-01 probe exercising RFC 0013 WebSocket streaming invariants in-process and on TCP."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from agnara import Agnara, AnonymousPrincipal, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import ExecutionPlan

from .loopback import LoopbackWebSocketClient, LoopbackWebSocketServer
from .projection import WebSocketStreamProjection

_SECRET_DIAGNOSTIC = "C:/private/ws-internal-token-secret"
_ALLOWED_ORIGIN = "https://app.example"


@dataclass
class _InvocationResource:
    serial: int
    loop: asyncio.AbstractEventLoop
    closed: bool = False


@dataclass
class _SingletonResource:
    loop: asyncio.AbstractEventLoop
    closed: bool = False


class _HarnessASGI:
    """In-memory ASGI 3.0 WebSocket driver recording emitted frames."""

    def __init__(
        self,
        app: WebSocketStreamProjection,
        headers: list[tuple[bytes, bytes]] | None = None,
        query: bytes = b"",
    ) -> None:
        self.app = app
        self.headers = (
            headers if headers is not None else [(b"origin", _ALLOWED_ORIGIN.encode("ascii"))]
        )
        self.query = query
        self.incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self.send_gate: asyncio.Event | None = None

    async def run(self, preloaded: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        await self.incoming.put({"type": "websocket.connect"})
        for item in preloaded or []:
            await self.incoming.put(item)

        async def receive() -> dict[str, Any]:
            return await self.incoming.get()

        async def send(message: dict[str, Any]) -> None:
            self.sent.append(message)
            if self.send_gate is not None and message["type"] == "websocket.send":
                await self.send_gate.wait()

        scope = {
            "type": "websocket",
            "path": "/ws",
            "query_string": self.query,
            "headers": self.headers,
        }
        await self.app(scope, receive, send)
        return self.sent


def _decoded_texts(sent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [json.loads(item["text"]) for item in sent if item["type"] == "websocket.send"]


def _closes(sent: list[dict[str, Any]]) -> list[int]:
    return [int(item["code"]) for item in sent if item["type"] == "websocket.close"]


def _accepted(sent: list[dict[str, Any]]) -> bool:
    return any(item["type"] == "websocket.accept" for item in sent)


async def _scenario_origin_rejected(
    plan: ExecutionPlan, registry: DIRegistry, tracker: list[_InvocationResource]
) -> dict[str, Any]:
    container = DIContainer(registry)
    try:
        proj = WebSocketStreamProjection(
            plan,
            container,
            allowed_origins=frozenset({_ALLOWED_ORIGIN}),
            principals=lambda _scope: Principal("ws-user", scopes={"stream:read"}),
        )
        missing = await _HarnessASGI(proj, headers=[]).run()
        untrusted = await _HarnessASGI(proj, headers=[(b"origin", b"https://evil.example")]).run()
        assert not _accepted(missing) and _closes(missing) == [1008]
        assert not _accepted(untrusted) and _closes(untrusted) == [1008]
        assert tracker == []
        return {"missing_close": 1008, "untrusted_close": 1008, "di_opens": 0}
    finally:
        await container.aclose()


async def _scenario_policy_denied_before_di(
    plan: ExecutionPlan, registry: DIRegistry, tracker: list[_InvocationResource]
) -> dict[str, Any]:
    container = DIContainer(registry)
    try:
        proj_a = WebSocketStreamProjection(
            plan,
            container,
            allowed_origins=frozenset({_ALLOWED_ORIGIN}),
            principals=lambda _scope: AnonymousPrincipal(),
            input_mode="handshake",
        )
        sent_a = await _HarnessASGI(proj_a, query=b"count=2").run()
        assert not _accepted(sent_a) and _closes(sent_a) == [1008]

        proj_b = WebSocketStreamProjection(
            plan,
            container,
            allowed_origins=frozenset({_ALLOWED_ORIGIN}),
            principals=lambda _scope: Principal("no-scope"),
            input_mode="initial_frame",
        )
        sent_b = await _HarnessASGI(proj_b).run(
            [{"type": "websocket.receive", "text": '{"count": 2}'}]
        )
        assert _accepted(sent_b)
        texts_b = _decoded_texts(sent_b)
        assert texts_b == [
            {
                "type": "terminal",
                "outcome": "failed",
                "units": 0,
                "error": {"code": "forbidden", "message": "required scopes not granted"},
            }
        ]
        assert _closes(sent_b) == [1008]
        assert tracker == []
        return {"option_a_pre_accept_close": 1008, "option_b_outcome": "forbidden", "di_opens": 0}
    finally:
        await container.aclose()


async def _scenario_option_a_streams(
    plan: ExecutionPlan, registry: DIRegistry, tracker: list[_InvocationResource]
) -> dict[str, Any]:
    container = DIContainer(registry)
    try:
        proj = WebSocketStreamProjection(
            plan,
            container,
            allowed_origins=frozenset({_ALLOWED_ORIGIN}),
            principals=lambda _scope: Principal("reader", scopes={"stream:read"}),
            input_mode="handshake",
        )
        sent = await _HarnessASGI(proj, query=b"count=3").run()
        assert _accepted(sent) and _closes(sent) == [1000]
        assert _decoded_texts(sent) == [
            {"type": "unit", "data": 10},
            {"type": "unit", "data": 20},
            {"type": "unit", "data": 30},
            {"type": "terminal", "outcome": "completed", "units": 3},
        ]
        empty_sent = await _HarnessASGI(proj, query=b"count=0").run()
        assert _accepted(empty_sent) and _closes(empty_sent) == [1000]
        assert _decoded_texts(empty_sent) == [
            {"type": "terminal", "outcome": "completed", "units": 0}
        ]
        assert len(tracker) == 2 and all(res.closed for res in tracker)
        return {"nonempty_units": 3, "empty_units": 0, "di_closed": 2}
    finally:
        await container.aclose()


async def _scenario_option_b_input_contracts(
    plan: ExecutionPlan, registry: DIRegistry, tracker: list[_InvocationResource]
) -> dict[str, Any]:
    container = DIContainer(registry)
    try:
        proj = WebSocketStreamProjection(
            plan,
            container,
            allowed_origins=frozenset({_ALLOWED_ORIGIN}),
            principals=lambda _scope: Principal("reader", scopes={"stream:read"}),
            input_mode="initial_frame",
            max_frame_bytes=256,
        )
        ok_sent = await _HarnessASGI(proj).run(
            [{"type": "websocket.receive", "text": '{"count": 2}'}]
        )
        assert _decoded_texts(ok_sent) == [
            {"type": "unit", "data": 10},
            {"type": "unit", "data": 20},
            {"type": "terminal", "outcome": "completed", "units": 2},
        ]
        assert _closes(ok_sent) == [1000]

        bad_bool = await _HarnessASGI(proj).run(
            [{"type": "websocket.receive", "text": '{"count": true}'}]
        )
        assert _decoded_texts(bad_bool)[0]["error"]["code"] == "invalid_input"
        assert _closes(bad_bool) == [1008]

        too_big = await _HarnessASGI(proj).run(
            [{"type": "websocket.receive", "text": '{"count": 1, "pad": "' + ("x" * 300) + '"}'}]
        )
        assert _closes(too_big) == [1009]
        assert len(tracker) == 1 and tracker[0].closed
        return {"ok_units": 2, "invalid_close": 1008, "oversized_initial_close": 1009}
    finally:
        await container.aclose()


async def _scenario_redaction_and_oversize(
    failing_plan: ExecutionPlan,
    big_unit_plan: ExecutionPlan,
    registry: DIRegistry,
    tracker: list[_InvocationResource],
) -> dict[str, Any]:
    container = DIContainer(registry)
    try:
        proj_fail = WebSocketStreamProjection(
            failing_plan,
            container,
            allowed_origins=frozenset({_ALLOWED_ORIGIN}),
            principals=lambda _scope: Principal("reader", scopes={"stream:read"}),
            input_mode="initial_frame",
        )
        pre_fail = await _HarnessASGI(proj_fail).run(
            [{"type": "websocket.receive", "text": '{"emit_before_fail": 0}'}]
        )
        mid_fail = await _HarnessASGI(proj_fail).run(
            [{"type": "websocket.receive", "text": '{"emit_before_fail": 1}'}]
        )
        assert _SECRET_DIAGNOSTIC not in json.dumps(pre_fail)
        assert _SECRET_DIAGNOSTIC not in json.dumps(mid_fail)
        assert _decoded_texts(pre_fail) == [
            {
                "type": "terminal",
                "outcome": "failed",
                "units": 0,
                "error": {"code": "internal_failure", "message": "capability invocation failed"},
            }
        ]
        assert _decoded_texts(mid_fail) == [
            {"type": "unit", "data": 10},
            {
                "type": "terminal",
                "outcome": "interrupted",
                "units": 1,
                "error": {"code": "internal_failure", "message": "capability invocation failed"},
            },
        ]
        assert _closes(pre_fail) == [1011] and _closes(mid_fail) == [1011]

        proj_big = WebSocketStreamProjection(
            big_unit_plan,
            container,
            allowed_origins=frozenset({_ALLOWED_ORIGIN}),
            principals=lambda _scope: Principal("reader", scopes={"stream:read"}),
            input_mode="initial_frame",
            max_frame_bytes=128,
        )
        big_sent = await _HarnessASGI(proj_big).run([{"type": "websocket.receive", "text": "{}"}])
        assert _decoded_texts(big_sent) == [
            {
                "type": "terminal",
                "outcome": "failed",
                "units": 0,
                "error": {"code": "internal_failure", "message": "capability invocation failed"},
            }
        ]
        assert _closes(big_sent) == [1011]
        assert len(tracker) == 3 and all(res.closed for res in tracker)
        return {
            "redacted": True,
            "pre_fail_units": 0,
            "mid_fail_units": 1,
            "oversize_unit_refused": True,
        }
    finally:
        await container.aclose()


async def _scenario_backpressure_and_disconnect() -> dict[str, Any]:
    trace: list[str] = []
    block_unit2 = asyncio.Event()
    blocked_entered = asyncio.Event()
    closed_event = asyncio.Event()
    tracker: list[_InvocationResource] = []

    @provider(scope=Scope.INVOCATION)
    async def acquire() -> AsyncIterator[_InvocationResource]:
        res = _InvocationResource(len(tracker) + 1, asyncio.get_running_loop())
        tracker.append(res)
        try:
            yield res
        finally:
            res.closed = True
            closed_event.set()

    app = Agnara("ws_flow")

    @app.capability(scopes=("stream:read",), streaming=True, output=int)
    async def controlled(count: int, res: _InvocationResource) -> AsyncIterator[int]:
        del res
        for idx in range(1, count + 1):
            trace.append(f"before_yield_{idx}")
            if idx == 2:
                blocked_entered.set()
                await block_unit2.wait()
            yield idx * 10
            trace.append(f"after_yield_{idx}")

    registry = DIRegistry()
    registry.bind(_InvocationResource, acquire)
    compiled = app.compile()
    plan = ExecutionPlan.compile(compiled["ws_flow.controlled"], registry)
    container = DIContainer(registry)
    try:
        proj = WebSocketStreamProjection(
            plan,
            container,
            allowed_origins=frozenset({_ALLOWED_ORIGIN}),
            principals=lambda _scope: Principal("reader", scopes={"stream:read"}),
            input_mode="initial_frame",
        )
        harness = _HarnessASGI(proj)
        harness.send_gate = asyncio.Event()
        task = asyncio.create_task(
            harness.run([{"type": "websocket.receive", "text": '{"count": 2}'}])
        )
        # Wait until accept + unit 1 send blocks inside send_gate.
        while len([m for m in harness.sent if m["type"] == "websocket.send"]) < 1:
            await asyncio.sleep(0)
        assert "before_yield_2" not in trace
        harness.send_gate.set()
        await blocked_entered.wait()
        await harness.incoming.put({"type": "websocket.disconnect", "code": 1001})
        await asyncio.wait_for(task, timeout=2.0)
        await asyncio.wait_for(closed_event.wait(), timeout=2.0)
        assert tracker[0].closed
        assert "after_yield_2" not in trace
        return {"zero_prefetch_verified": True, "disconnect_cancelled_producer": True}
    finally:
        await container.aclose()


async def _scenario_deadline_and_concurrency() -> dict[str, Any]:
    tracker: list[_InvocationResource] = []
    singleton_holder: list[_SingletonResource] = []
    entered = {1: asyncio.Event(), 2: asyncio.Event()}
    release = {1: asyncio.Event(), 2: asyncio.Event()}

    @provider(scope=Scope.SINGLETON)
    async def acquire_singleton() -> AsyncIterator[_SingletonResource]:
        singleton = _SingletonResource(asyncio.get_running_loop())
        singleton_holder.append(singleton)
        try:
            yield singleton
        finally:
            singleton.closed = True

    @provider(scope=Scope.INVOCATION)
    async def acquire_invocation() -> AsyncIterator[_InvocationResource]:
        res = _InvocationResource(len(tracker) + 1, asyncio.get_running_loop())
        tracker.append(res)
        try:
            yield res
        finally:
            res.closed = True

    app = Agnara("ws_concurrent")

    @app.capability(scopes=("stream:read",), streaming=True, output=int)
    async def hold_stream(
        slot: int,
        res: _InvocationResource,
        singleton: _SingletonResource,
    ) -> AsyncIterator[int]:
        assert not res.closed and not singleton.closed
        yield slot
        entered[slot].set()
        await release[slot].wait()
        yield slot * 10

    registry = DIRegistry()
    registry.bind(_SingletonResource, acquire_singleton)
    registry.bind(_InvocationResource, acquire_invocation)
    compiled = app.compile()
    plan = ExecutionPlan.compile(compiled["ws_concurrent.hold_stream"], registry)
    container = DIContainer(registry)
    try:
        # 1. Deadline expiration after first unit -> timed_out + 1011
        proj_timeout = WebSocketStreamProjection(
            plan,
            container,
            allowed_origins=frozenset({_ALLOWED_ORIGIN}),
            principals=lambda _scope: Principal("reader", scopes={"stream:read"}),
            attempt_timeout=0.05,
        )
        timed = await _HarnessASGI(proj_timeout).run(
            [{"type": "websocket.receive", "text": '{"slot": 1}'}]
        )
        texts = _decoded_texts(timed)
        assert texts == [
            {"type": "unit", "data": 1},
            {
                "type": "terminal",
                "outcome": "timed_out",
                "units": 1,
                "error": {"code": "timeout", "message": "invocation deadline exceeded"},
            },
        ]
        assert _closes(timed) == [1011] and tracker[0].closed and not singleton_holder[0].closed

        # 2. Concurrent isolated streams sharing one live singleton
        entered[1].clear()
        proj_conc = WebSocketStreamProjection(
            plan,
            container,
            allowed_origins=frozenset({_ALLOWED_ORIGIN}),
            principals=lambda _scope: Principal("reader", scopes={"stream:read"}),
        )
        h1, h2 = _HarnessASGI(proj_conc), _HarnessASGI(proj_conc)
        t1 = asyncio.create_task(h1.run([{"type": "websocket.receive", "text": '{"slot": 1}'}]))
        t2 = asyncio.create_task(h2.run([{"type": "websocket.receive", "text": '{"slot": 2}'}]))
        await entered[1].wait()
        await entered[2].wait()
        r1, r2 = tracker[1], tracker[2]
        assert r1 is not r2 and not r1.closed and not r2.closed
        release[1].set()
        await t1
        assert r1.closed and not r2.closed and not singleton_holder[0].closed
        release[2].set()
        await t2
        assert r2.closed and not singleton_holder[0].closed
    finally:
        await container.aclose()
    assert singleton_holder[0].closed
    return {
        "deadline_outcome": "timed_out",
        "concurrent_isolated": True,
        "singleton_lifetime_preserved": True,
    }


async def _scenario_tcp_loopback_rfc6455() -> dict[str, Any]:
    tracker: list[_InvocationResource] = []
    entered = asyncio.Event()
    closed = asyncio.Event()
    block_forever = asyncio.Event()

    @provider(scope=Scope.INVOCATION)
    async def acquire() -> AsyncIterator[_InvocationResource]:
        res = _InvocationResource(len(tracker) + 1, asyncio.get_running_loop())
        tracker.append(res)
        try:
            yield res
        finally:
            res.closed = True
            closed.set()

    app = Agnara("ws_tcp")

    @app.capability(scopes=("stream:read",), streaming=True, output=int)
    async def stream_or_wait(wait: bool, res: _InvocationResource) -> AsyncIterator[int]:
        del res
        yield 7
        if wait:
            entered.set()
            await block_forever.wait()
        yield 14

    registry = DIRegistry()
    registry.bind(_InvocationResource, acquire)
    compiled = app.compile()
    plan = ExecutionPlan.compile(compiled["ws_tcp.stream_or_wait"], registry)
    container = DIContainer(registry)
    proj = WebSocketStreamProjection(
        plan,
        container,
        allowed_origins=frozenset({_ALLOWED_ORIGIN}),
        principals=lambda _scope: Principal("reader", scopes={"stream:read"}),
        input_mode="initial_frame",
    )
    server = LoopbackWebSocketServer(proj)
    port = await server.start()
    try:
        # 1. Pre-upgrade 403 on bad Origin
        bad_status, bad_client = await LoopbackWebSocketClient.open(
            port, headers={"Origin": "https://evil.example"}
        )
        assert bad_status == 403 and bad_client is None and tracker == []

        # 2. Normal completed TCP stream
        ok_status, client = await LoopbackWebSocketClient.open(
            port, headers={"Origin": _ALLOWED_ORIGIN}
        )
        assert ok_status == 101 and client is not None
        await client.send_text('{"wait": false}')
        events = [await client.recv_event() for _ in range(4)]
        await client.abort_tcp()
        assert events == [
            ("text", {"type": "unit", "data": 7}),
            ("text", {"type": "unit", "data": 14}),
            ("text", {"type": "terminal", "outcome": "completed", "units": 2}),
            ("close", 1000),
        ]

        # 3. Abrupt TCP disconnect cancels suspended producer
        closed.clear()
        drop_status, drop_client = await LoopbackWebSocketClient.open(
            port, headers={"Origin": _ALLOWED_ORIGIN}
        )
        assert drop_status == 101 and drop_client is not None
        await drop_client.send_text('{"wait": true}')
        assert await drop_client.recv_event() == ("text", {"type": "unit", "data": 7})
        await asyncio.wait_for(entered.wait(), timeout=2.0)
        await drop_client.abort_tcp()
        await asyncio.wait_for(closed.wait(), timeout=2.0)
        assert len(tracker) == 2 and all(res.closed for res in tracker)
        return {"bad_origin_http": 403, "loopback_units": 2, "abrupt_tcp_drop_cleaned": True}
    finally:
        await server.aclose()
        await container.aclose()


async def run_probe() -> dict[str, Any]:
    """Execute all WS-01 scenarios on one loop and assert zero leaked tasks."""
    tracker: list[_InvocationResource] = []

    @provider(scope=Scope.INVOCATION)
    async def acquire() -> AsyncIterator[_InvocationResource]:
        res = _InvocationResource(len(tracker) + 1, asyncio.get_running_loop())
        tracker.append(res)
        try:
            yield res
        finally:
            assert res.loop is asyncio.get_running_loop()
            res.closed = True

    app = Agnara("ws_probe")

    @app.capability(scopes=("stream:read",), streaming=True, output=int)
    async def numbers(count: int, res: _InvocationResource) -> AsyncIterator[int]:
        del res
        for idx in range(1, count + 1):
            yield idx * 10

    @app.capability(scopes=("stream:read",), streaming=True, output=int)
    async def failing(emit_before_fail: int, res: _InvocationResource) -> AsyncIterator[int]:
        del res
        if emit_before_fail:
            yield 10
        raise RuntimeError(_SECRET_DIAGNOSTIC)

    @app.capability(scopes=("stream:read",), streaming=True, output=str)
    async def oversized(res: _InvocationResource) -> AsyncIterator[str]:
        del res
        yield "x" * 128

    registry = DIRegistry()
    registry.bind(_InvocationResource, acquire)
    compiled = app.compile()
    numbers_plan = ExecutionPlan.compile(compiled["ws_probe.numbers"], registry)
    failing_plan = ExecutionPlan.compile(compiled["ws_probe.failing"], registry)
    oversized_plan = ExecutionPlan.compile(compiled["ws_probe.oversized"], registry)

    results: dict[str, Any] = {}
    results["origin_rejected_before_accept"] = await _scenario_origin_rejected(
        numbers_plan, registry, tracker
    )
    tracker.clear()
    results["policy_denied_before_di"] = await _scenario_policy_denied_before_di(
        numbers_plan, registry, tracker
    )
    tracker.clear()
    results["option_a_completed_and_empty"] = await _scenario_option_a_streams(
        numbers_plan, registry, tracker
    )
    tracker.clear()
    results["option_b_input_contracts"] = await _scenario_option_b_input_contracts(
        numbers_plan, registry, tracker
    )
    tracker.clear()
    results["redaction_and_oversize"] = await _scenario_redaction_and_oversize(
        failing_plan, oversized_plan, registry, tracker
    )
    results["backpressure_and_disconnect"] = await _scenario_backpressure_and_disconnect()
    results["deadline_and_concurrency"] = await _scenario_deadline_and_concurrency()
    results["tcp_loopback_rfc6455"] = await _scenario_tcp_loopback_rfc6455()

    await asyncio.sleep(0)
    surviving = len(asyncio.all_tasks()) - 1
    assert surviving == 0, f"leaked asyncio tasks: {surviving}"
    return {
        "experiment": "WS-01",
        "python": ".".join(map(str, sys.version_info[:3])),
        "surviving_tasks": surviving,
        "scenarios": results,
    }


def main() -> int:
    with contextlib.suppress(KeyboardInterrupt):
        output = asyncio.run(run_probe())
        print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
