"""Conformance tests for EVT-03 settlement outcomes, stop races, and cleanup."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import ExecutionPlan, Failure, FailureCode
from agnara_events._consumer import (
    _consume_inbound_events,
    _ConsumerBudgets,
    _ConsumerDiagnostic,
    _SettlementUncertaintyError,
)
from agnara_events._envelope import CLOUDEVENTS_JSON_CONTENT_TYPE
from agnara_events._exposure import _compile_inbound_event, _declare_inbound_event


class _Store:
    pass


class _Conn:
    pass


class FakeDelivery:
    def __init__(
        self,
        body: bytes,
        *,
        content_type: str | None = CLOUDEVENTS_JSON_CONTENT_TYPE,
        fail_on: str | None = None,
    ) -> None:
        self.body = body
        self.content_type = content_type
        self.fail_on = fail_on
        self.settlements: list[str] = []

    async def acknowledge(self) -> None:
        if self.fail_on == "acknowledge":
            raise OSError("broker socket secret-host:5672 closed")
        self.settlements.append("acknowledge")

    async def reject(self) -> None:
        if self.fail_on == "reject":
            raise OSError("broker reject failed on secret-queue")
        self.settlements.append("reject")

    async def release(self) -> None:
        if self.fail_on == "release":
            raise OSError("broker release failed on secret-queue")
        self.settlements.append("release")


class FakeDeliverySource:
    def __init__(self, deliveries: list[FakeDelivery] | None = None) -> None:
        self._queue: asyncio.Queue[FakeDelivery | None] = asyncio.Queue()
        for item in deliveries or []:
            self._queue.put_nowait(item)
        self.stopped = False
        self.stopped_event = asyncio.Event()
        self.stop_calls = 0
        self.receive_calls = 0

    def push(self, item: FakeDelivery | None) -> None:
        self._queue.put_nowait(item)

    async def receive(self) -> FakeDelivery | None:
        self.receive_calls += 1
        return await self._queue.get()

    async def stop_receiving(self) -> None:
        self.stopped = True
        self.stop_calls += 1
        self.stopped_event.set()


def _ce(
    data: dict[str, object],
    *,
    event_type: str = "evt.op.v1",
    extra: dict[str, object] | None = None,
) -> bytes:
    payload: dict[str, object] = {
        "specversion": "1.0",
        "id": "id-1",
        "source": "/src",
        "type": event_type,
        "data": data,
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload).encode("utf-8")


@pytest.mark.parametrize(
    ("mode", "expected_outcome", "expected_settlement", "expect_resource"),
    [
        ("success", "success", "acknowledge", True),
        ("invalid_input", "invalid_input", "reject", False),
        ("unauthenticated", "unauthenticated", "reject", True),
        ("forbidden", "forbidden", "reject", False),
        ("interaction_required", "interaction_required", "reject", True),
        ("not_found", "not_found", "reject", True),
        ("conflict", "conflict", "reject", True),
        ("rate_limited", "rate_limited", "release", True),
        ("unavailable", "unavailable", "release", True),
        ("timeout", "timeout", "release", True),
        ("internal_failure", "internal_failure", "release", True),
    ],
)
def test_every_canonical_outcome_maps_to_adr0101_settlement(
    mode: str,
    expected_outcome: str,
    expected_settlement: str,
    expect_resource: bool,
) -> None:
    async def run() -> None:
        events: list[str] = []
        app = Agnara("orders")

        @provider(scope=Scope.INVOCATION)
        async def open_store() -> AsyncIterator[_Store]:
            events.append("store.open")
            try:
                yield _Store()
            finally:
                events.append("store.close")

        @app.capability(scopes=("orders:write",), output=str)
        async def handle(action: str, count: int, store: _Store) -> str | Failure:
            events.append(f"handler:{action}:{count}")
            if action == "success":
                return "secret-return-value-must-be-discarded"
            if action == "internal_failure":
                raise RuntimeError("secret-db-password-leak")
            return Failure(FailureCode(action), "operation diagnostic")

        compiled = app.compile()
        deps = DIRegistry()
        deps.bind(_Store, open_store)
        cap_def = compiled["orders.handle"]
        plan = ExecutionPlan.compile(cap_def, deps)
        container = DIContainer(deps)

        principal_scopes = frozenset() if mode == "forbidden" else frozenset({"orders:write"})
        principal = Principal("svc-consumer", scopes=principal_scopes)
        exposure = _declare_inbound_event(
            cap_def,
            subscription_id="orders-sub",
            event_type="evt.op.v1",
            principal=principal,
        )
        binding = _compile_inbound_event(exposure, {cap_def.id: plan})

        if mode == "invalid_input":
            # Lexically integral float 2.0 must fail strict Python int validation.
            body = _ce({"action": "success", "count": 2.0})
        else:
            body = _ce({"action": mode, "count": 9007199254740993})

        delivery = FakeDelivery(body)
        source = FakeDeliverySource([delivery])
        source.push(None)

        recorded: list[_ConsumerDiagnostic] = []
        try:
            diagnostics = await _consume_inbound_events(
                binding,
                container,
                source,
                budgets=_ConsumerBudgets(attempt_seconds=5.0, shutdown_seconds=1.0),
                stop_event=asyncio.Event(),
                on_diagnostic=recorded.append,
            )
        finally:
            await container.aclose()

        assert len(diagnostics) == 1
        assert diagnostics == tuple(recorded)
        diag = diagnostics[0]
        assert diag.subscription_id == "orders-sub"
        assert diag.outcome == expected_outcome
        assert diag.settlement == expected_settlement
        assert delivery.settlements == [expected_settlement]
        assert "secret-db-password-leak" not in str(diag)
        assert "secret-return-value-must-be-discarded" not in str(diag)

        if expect_resource:
            assert events[0] == "store.open"
            assert events[-1] == "store.close"
        else:
            assert events == []

    asyncio.run(run())


def test_malformed_envelope_and_forged_producer_attributes_acquire_nothing() -> None:
    async def run() -> None:
        acquisitions = 0
        app = Agnara("inventory")

        @provider(scope=Scope.INVOCATION)
        async def open_store() -> AsyncIterator[_Store]:
            nonlocal acquisitions
            acquisitions += 1
            yield _Store()

        @app.capability(scopes=("inventory:write",), output=str)
        async def apply(sku: str, store: _Store) -> str:
            return sku

        compiled = app.compile()
        deps = DIRegistry()
        deps.bind(_Store, open_store)
        cap_def = compiled["inventory.apply"]
        plan = ExecutionPlan.compile(cap_def, deps)
        container = DIContainer(deps)

        # Principal lacks inventory:write; producer attributes cannot grant it.
        unscoped = Principal("svc-no-scope", scopes=())
        binding = _compile_inbound_event(
            _declare_inbound_event(
                cap_def,
                subscription_id="inv-sub",
                event_type="evt.inv.v1",
                principal=unscoped,
            ),
            {cap_def.id: plan},
        )
        # 1) Wrong type -> reject without entering policy/DI
        wrong_type = FakeDelivery(_ce({"sku": "A"}, event_type="wrong.type"))
        # 2) Producer tries to assert scopes/principal in envelope -> still forbidden
        forged_attr = FakeDelivery(
            _ce(
                {"sku": "A"},
                event_type="evt.inv.v1",
                extra={"scopes": ["inventory:write"], "principal": "admin"},
            )
        )
        source = FakeDeliverySource([wrong_type, forged_attr])
        source.push(None)

        try:
            diags = await _consume_inbound_events(
                binding,
                container,
                source,
                budgets=_ConsumerBudgets(attempt_seconds=2.0, shutdown_seconds=1.0),
                stop_event=asyncio.Event(),
            )
        finally:
            await container.aclose()

        assert acquisitions == 0
        assert [d.outcome for d in diags] == ["type_mismatch", "forbidden"]
        assert wrong_type.settlements == ["reject"]
        assert forged_attr.settlements == ["reject"]

        # 3) Even with an authorized principal, forged dependency parameter fails validation.
        authorized_binding = _compile_inbound_event(
            _declare_inbound_event(
                cap_def,
                subscription_id="inv-sub",
                event_type="evt.inv.v1",
                principal=Principal("svc-ok", scopes={"inventory:write"}),
            ),
            {cap_def.id: plan},
        )
        forged_dep = FakeDelivery(_ce({"sku": "A", "store": "forged"}, event_type="evt.inv.v1"))
        source2 = FakeDeliverySource([forged_dep])
        source2.push(None)
        container2 = DIContainer(deps)
        try:
            diags2 = await _consume_inbound_events(
                authorized_binding,
                container2,
                source2,
                budgets=_ConsumerBudgets(attempt_seconds=2.0, shutdown_seconds=1.0),
                stop_event=asyncio.Event(),
            )
        finally:
            await container2.aclose()

        assert acquisitions == 0
        assert [d.outcome for d in diags2] == ["invalid_input"]
        assert forged_dep.settlements == ["reject"]

    asyncio.run(run())


def test_shutdown_within_budget_completes_and_acknowledges_before_container_close() -> None:
    async def run() -> None:
        trace: list[str] = []
        entered = asyncio.Event()
        allow_finish = asyncio.Event()
        app = Agnara("jobs")

        @provider(scope=Scope.INVOCATION)
        async def open_conn() -> AsyncIterator[_Conn]:
            trace.append("conn.open")
            try:
                yield _Conn()
            finally:
                trace.append("conn.close")

        @app.capability(output=str)
        async def job(name: str, conn: _Conn) -> str:
            trace.append("handler.enter")
            entered.set()
            await allow_finish.wait()
            trace.append("handler.exit")
            return name

        compiled = app.compile()
        deps = DIRegistry()
        deps.bind(_Conn, open_conn)
        plan = ExecutionPlan.compile(compiled["jobs.job"], deps)
        container = DIContainer(deps)
        binding = _compile_inbound_event(
            _declare_inbound_event(
                compiled["jobs.job"],
                subscription_id="jobs-sub",
                event_type="evt.job.v1",
                principal=Principal("worker"),
            ),
            {compiled["jobs.job"].id: plan},
        )

        delivery = FakeDelivery(_ce({"name": "ok"}, event_type="evt.job.v1"))
        source = FakeDeliverySource([delivery])
        stop_event = asyncio.Event()

        before_tasks = asyncio.all_tasks()
        async with asyncio.TaskGroup() as group:
            consumer_task = group.create_task(
                _consume_inbound_events(
                    binding,
                    container,
                    source,
                    budgets=_ConsumerBudgets(attempt_seconds=5.0, shutdown_seconds=2.0),
                    stop_event=stop_event,
                )
            )
            await entered.wait()
            stop_event.set()
            async with asyncio.timeout(2.0):
                await source.stopped_event.wait()
            assert source.stopped
            allow_finish.set()

        await container.aclose()
        trace.append("container.close")

        assert asyncio.all_tasks() == before_tasks
        diags = consumer_task.result()
        assert len(diags) == 1
        assert diags[0].outcome == "success"
        assert diags[0].settlement == "acknowledge"
        assert delivery.settlements == ["acknowledge"]
        assert trace == [
            "conn.open",
            "handler.enter",
            "handler.exit",
            "conn.close",
            "container.close",
        ]

    asyncio.run(run())


def test_shutdown_budget_expiry_cancels_joins_cleans_up_and_releases_delivery() -> None:
    async def run() -> None:
        trace: list[str] = []
        entered = asyncio.Event()
        app = Agnara("jobs")

        @provider(scope=Scope.INVOCATION)
        async def open_conn() -> AsyncIterator[_Conn]:
            trace.append("conn.open")
            try:
                yield _Conn()
            finally:
                trace.append("conn.close")

        @app.capability(output=str)
        async def blocked(name: str, conn: _Conn) -> str:
            trace.append("handler.enter")
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                trace.append("handler.cancelled")
            return name

        compiled = app.compile()
        deps = DIRegistry()
        deps.bind(_Conn, open_conn)
        plan = ExecutionPlan.compile(compiled["jobs.blocked"], deps)
        container = DIContainer(deps)
        binding = _compile_inbound_event(
            _declare_inbound_event(
                compiled["jobs.blocked"],
                subscription_id="jobs-sub",
                event_type="evt.job.v1",
                principal=Principal("worker"),
            ),
            {compiled["jobs.blocked"].id: plan},
        )

        class TracingDelivery(FakeDelivery):
            async def release(self) -> None:
                trace.append("delivery.release")
                await super().release()

        delivery = TracingDelivery(_ce({"name": "slow"}, event_type="evt.job.v1"))
        source = FakeDeliverySource([delivery])
        stop_event = asyncio.Event()

        before_tasks = asyncio.all_tasks()
        async with asyncio.TaskGroup() as group:
            consumer_task = group.create_task(
                _consume_inbound_events(
                    binding,
                    container,
                    source,
                    budgets=_ConsumerBudgets(attempt_seconds=5.0, shutdown_seconds=0.02),
                    stop_event=stop_event,
                )
            )
            await entered.wait()
            stop_event.set()

        await container.aclose()
        trace.append("container.close")

        assert asyncio.all_tasks() == before_tasks
        diags = consumer_task.result()
        assert len(diags) == 1
        assert diags[0].outcome == "cancelled"
        assert diags[0].settlement == "release"
        # Handler and invocation dependency must close BEFORE delivery release and container close.
        assert trace == [
            "conn.open",
            "handler.enter",
            "handler.cancelled",
            "conn.close",
            "delivery.release",
            "container.close",
        ]

    asyncio.run(run())


def test_stop_racing_with_receive_releases_unstarted_delivery() -> None:
    async def run() -> None:
        handler_calls = 0
        app = Agnara("jobs")

        @app.capability(output=str)
        async def noop(x: str) -> str:
            nonlocal handler_calls
            handler_calls += 1
            return x

        compiled = app.compile()
        plan = ExecutionPlan.compile(compiled["jobs.noop"], DIRegistry())
        container = DIContainer(DIRegistry())
        binding = _compile_inbound_event(
            _declare_inbound_event(
                compiled["jobs.noop"],
                subscription_id="jobs-sub",
                event_type="evt.job.v1",
                principal=Principal("worker"),
            ),
            {compiled["jobs.noop"].id: plan},
        )

        delivery = FakeDelivery(_ce({"x": "1"}, event_type="evt.job.v1"))
        source = FakeDeliverySource([delivery])
        stop_event = asyncio.Event()
        stop_event.set()

        try:
            diags = await _consume_inbound_events(
                binding,
                container,
                source,
                budgets=_ConsumerBudgets(attempt_seconds=1.0, shutdown_seconds=1.0),
                stop_event=stop_event,
            )
        finally:
            await container.aclose()

        assert handler_calls == 0
        assert diags == ()
        assert source.stopped
        assert source.receive_calls == 0
        assert delivery.settlements == []

    asyncio.run(run())


def test_settlement_failure_stops_consumption_and_redacts_broker_exception() -> None:
    async def run() -> None:
        app = Agnara("jobs")

        @app.capability(output=str)
        async def ok(x: str) -> str:
            return x

        compiled = app.compile()
        plan = ExecutionPlan.compile(compiled["jobs.ok"], DIRegistry())
        container = DIContainer(DIRegistry())
        binding = _compile_inbound_event(
            _declare_inbound_event(
                compiled["jobs.ok"],
                subscription_id="jobs-sub",
                event_type="evt.job.v1",
                principal=Principal("worker"),
            ),
            {compiled["jobs.ok"].id: plan},
        )

        first = FakeDelivery(_ce({"x": "1"}, event_type="evt.job.v1"), fail_on="acknowledge")
        second = FakeDelivery(_ce({"x": "2"}, event_type="evt.job.v1"))
        source = FakeDeliverySource([first, second])

        try:
            with pytest.raises(_SettlementUncertaintyError) as exc_info:
                await _consume_inbound_events(
                    binding,
                    container,
                    source,
                    budgets=_ConsumerBudgets(attempt_seconds=2.0, shutdown_seconds=1.0),
                    stop_event=asyncio.Event(),
                )
        finally:
            await container.aclose()

        err = exc_info.value
        assert err.subscription_id == "jobs-sub"
        assert err.outcome == "success"
        assert err.intended_action == "acknowledge"
        assert "secret-host:5672" not in str(err)
        assert source.receive_calls == 1
        assert second.settlements == []

    asyncio.run(run())


def test_external_cancellation_propagates_and_releases_unfinished_delivery() -> None:
    async def run() -> None:
        entered = asyncio.Event()
        app = Agnara("jobs")

        @app.capability(output=str)
        async def wait_forever(x: str) -> str:
            entered.set()
            await asyncio.Event().wait()
            return x

        compiled = app.compile()
        plan = ExecutionPlan.compile(compiled["jobs.wait_forever"], DIRegistry())
        container = DIContainer(DIRegistry())
        binding = _compile_inbound_event(
            _declare_inbound_event(
                compiled["jobs.wait_forever"],
                subscription_id="jobs-sub",
                event_type="evt.job.v1",
                principal=Principal("worker"),
            ),
            {compiled["jobs.wait_forever"].id: plan},
        )

        delivery = FakeDelivery(_ce({"x": "1"}, event_type="evt.job.v1"))
        source = FakeDeliverySource([delivery])
        before = asyncio.all_tasks()

        task = asyncio.create_task(
            _consume_inbound_events(
                binding,
                container,
                source,
                budgets=_ConsumerBudgets(attempt_seconds=10.0, shutdown_seconds=1.0),
                stop_event=asyncio.Event(),
            )
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await container.aclose()

        assert asyncio.all_tasks() == before
        assert source.stopped
        assert delivery.settlements == ["release"]

    asyncio.run(run())
