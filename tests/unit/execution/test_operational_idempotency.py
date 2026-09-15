"""Runtime behavior for the explicit ADR 0091 idempotency boundary."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, NoReturn

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId, Idempotency
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    IdempotencyInvocation,
    IdempotencyReservation,
    IdempotencyScope,
    IdempotencyStorageError,
    InMemoryIdempotencyStore,
    Invocation,
    InvocationStartEvent,
    InvocationTerminalEvent,
    Success,
    TelemetryHook,
    invoke_result,
)
from agnara.policy import Principal


class JsonCodec:
    def encode(self, value: object, /) -> bytes:
        return json.dumps(value, sort_keys=True).encode("utf-8")

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


CAPTURE = CapabilityId.parse("payments.capture")


def plan_for(
    handler: Callable[..., Any],
    *,
    idempotency: Idempotency = Idempotency.YES,
    hooks: tuple[TelemetryHook, ...] = (),
) -> ExecutionPlan:
    registry = DIRegistry()
    definition = CapabilityDefinition.declare(
        id=CAPTURE,
        handler=handler,
        idempotency=idempotency,
    )
    return ExecutionPlan.compile(definition, registry, hooks=hooks)


def context_for(
    plan: ExecutionPlan,
    store: InMemoryIdempotencyStore,
    *,
    key: str = "capture-1",
    fingerprint: bytes = b"capture-a",
    principal: Principal | None = None,
    scope_capability: CapabilityId = CAPTURE,
    scope_principal: str | None = None,
    codec: JsonCodec | None = None,
) -> ExecutionContext:
    resolved_principal = principal or Principal("customer-1")
    scope = IdempotencyScope(
        scope_capability,
        resolved_principal.identity if scope_principal is None else scope_principal,
        key,
        fingerprint,
    )
    return ExecutionContext(
        Invocation(plan.definition.id, {}, {}),
        DIContainer(DIRegistry()),
        principal=resolved_principal,
        idempotency=IdempotencyInvocation(
            scope, store, JsonCodec() if codec is None else codec, 30, 60
        ),
    )


def test_completed_duplicate_reuses_success_without_repeating_handler_effects() -> None:
    async def run() -> None:
        effects = 0

        def capture() -> dict[str, str]:
            nonlocal effects
            effects += 1
            return {"status": "captured"}

        plan = plan_for(capture)
        store = InMemoryIdempotencyStore()
        first_context = context_for(plan, store)
        duplicate_context = context_for(plan, store)

        first = await invoke_result(plan, first_context)
        duplicate = await invoke_result(plan, duplicate_context)

        assert first == Success({"status": "captured"})
        assert duplicate == Success({"status": "captured"})
        assert effects == 1
        assert duplicate_context.execution_id == first_context.execution_id
        assert duplicate.execution_id == first.execution_id == first_context.execution_id

    asyncio.run(run())


def test_simultaneous_duplicate_observes_in_progress_and_never_runs_handler_twice() -> None:
    async def run() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        effects = 0

        async def capture() -> str:
            nonlocal effects
            effects += 1
            if effects > 1:
                return "captured"
            started.set()
            await release.wait()
            return "captured"

        plan = plan_for(capture)
        store = InMemoryIdempotencyStore()
        first_task = asyncio.create_task(invoke_result(plan, context_for(plan, store)))
        await started.wait()
        duplicate = await invoke_result(plan, context_for(plan, store))
        release.set()
        first = await first_task

        assert duplicate == Failure(
            FailureCode.CONFLICT, "idempotency request is already in progress"
        )
        assert first == Success("captured")
        assert effects == 1

    asyncio.run(run())


def test_many_simultaneous_duplicates_never_run_effects_twice_and_reuse_after_completion() -> None:
    async def run() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        effects = 0

        async def capture() -> str:
            nonlocal effects
            effects += 1
            started.set()
            await release.wait()
            return "captured"

        plan = plan_for(capture)
        store = InMemoryIdempotencyStore()
        first_task = asyncio.create_task(invoke_result(plan, context_for(plan, store)))
        await started.wait()
        duplicates = await asyncio.gather(
            *(invoke_result(plan, context_for(plan, store)) for _ in range(32))
        )
        assert (
            duplicates
            == [Failure(FailureCode.CONFLICT, "idempotency request is already in progress")] * 32
        )
        assert effects == 1

        release.set()
        assert await first_task == Success("captured")
        assert await invoke_result(plan, context_for(plan, store)) == Success("captured")
        assert effects == 1

    asyncio.run(run())


def test_failure_releases_the_claim_for_a_later_explicit_attempt() -> None:
    async def run() -> None:
        effects = 0

        def capture() -> str:
            nonlocal effects
            effects += 1
            if effects == 1:
                raise RuntimeError("downstream failed")
            return "captured"

        plan = plan_for(capture)
        store = InMemoryIdempotencyStore()

        failed = await invoke_result(plan, context_for(plan, store))
        succeeded = await invoke_result(plan, context_for(plan, store))

        assert failed == Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")
        assert succeeded == Success("captured")
        assert effects == 2

    asyncio.run(run())


def test_cancellation_releases_the_claim_without_becoming_a_cached_failure() -> None:
    async def run() -> None:
        started = asyncio.Event()
        effects = 0

        async def capture() -> str:
            nonlocal effects
            effects += 1
            if effects > 1:
                return "captured"
            started.set()
            await asyncio.Event().wait()
            return "unreachable"

        plan = plan_for(capture)
        store = InMemoryIdempotencyStore()
        task = asyncio.create_task(invoke_result(plan, context_for(plan, store)))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        replacement = await invoke_result(plan, context_for(plan, store))

        assert replacement == Success("captured")
        assert effects == 2

    asyncio.run(run())


def test_completed_result_storage_failure_fails_closed_and_keeps_the_lease() -> None:
    class CompleteFailsStore(InMemoryIdempotencyStore):
        async def complete(
            self,
            reservation: IdempotencyReservation,
            result: bytes,
            *,
            result_ttl: float,
        ) -> bool:
            raise IdempotencyStorageError("unavailable")

    async def run() -> None:
        effects = 0

        def capture() -> str:
            nonlocal effects
            effects += 1
            return "captured"

        plan = plan_for(capture)
        store = CompleteFailsStore()

        failed = await invoke_result(plan, context_for(plan, store))
        duplicate = await invoke_result(plan, context_for(plan, store))

        assert failed == Failure(FailureCode.UNAVAILABLE, "idempotency storage is unavailable")
        assert duplicate == Failure(
            FailureCode.CONFLICT, "idempotency request is already in progress"
        )
        assert effects == 1

    asyncio.run(run())


def test_abandon_storage_failure_fails_closed_after_handler_failure() -> None:
    class AbandonFailsStore(InMemoryIdempotencyStore):
        async def abandon(self, reservation: IdempotencyReservation) -> bool:
            del reservation
            raise IdempotencyStorageError("unavailable")

    async def run() -> None:
        effects = 0

        def capture() -> str:
            nonlocal effects
            effects += 1
            raise RuntimeError("downstream failed")

        plan = plan_for(capture)
        store = AbandonFailsStore()

        assert await invoke_result(plan, context_for(plan, store)) == Failure(
            FailureCode.UNAVAILABLE, "idempotency storage is unavailable"
        )
        assert await invoke_result(plan, context_for(plan, store)) == Failure(
            FailureCode.CONFLICT, "idempotency request is already in progress"
        )
        assert effects == 1

    asyncio.run(run())


def test_cancellation_keeps_its_control_flow_when_abandoning_the_lease_fails() -> None:
    class AbandonFailsStore(InMemoryIdempotencyStore):
        async def abandon(self, reservation: IdempotencyReservation) -> bool:
            del reservation
            raise IdempotencyStorageError("unavailable")

    async def run() -> None:
        started = asyncio.Event()

        async def capture() -> str:
            started.set()
            await asyncio.Event().wait()
            return "unreachable"

        plan = plan_for(capture)
        store = AbandonFailsStore()
        task = asyncio.create_task(invoke_result(plan, context_for(plan, store)))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert await invoke_result(plan, context_for(plan, store)) == Failure(
            FailureCode.CONFLICT, "idempotency request is already in progress"
        )

    asyncio.run(run())


def test_stale_or_incompatible_completed_data_fails_closed_without_reexecuting() -> None:
    class OldCodec(JsonCodec):
        def decode(self, payload: bytes, /) -> object:
            del payload
            raise ValueError("obsolete schema payload contains secret")

    async def run() -> None:
        effects = 0

        def capture() -> str:
            nonlocal effects
            effects += 1
            return "captured"

        plan = plan_for(capture)
        store = InMemoryIdempotencyStore()
        assert await invoke_result(plan, context_for(plan, store)) == Success("captured")
        stale = await invoke_result(plan, context_for(plan, store, codec=OldCodec()))

        assert stale == Failure(FailureCode.UNAVAILABLE, "idempotency storage is unavailable")
        assert effects == 1

    asyncio.run(run())


def test_idempotent_telemetry_events_pair_on_the_claimed_logical_execution_identity() -> None:
    class Recorder(TelemetryHook):
        def __init__(self) -> None:
            self.starts: list[InvocationStartEvent] = []
            self.terminals: list[InvocationTerminalEvent] = []

        def on_invocation_start(self, event: InvocationStartEvent) -> None:
            self.starts.append(event)

        def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
            self.terminals.append(event)

    async def run() -> None:
        recorder = Recorder()
        plan = plan_for(lambda: "captured", hooks=(recorder,))
        store = InMemoryIdempotencyStore()
        first_context = context_for(plan, store)
        duplicate_context = context_for(plan, store)

        assert await invoke_result(plan, first_context) == Success("captured")
        assert await invoke_result(plan, duplicate_context) == Success("captured")

        execution_id = first_context.execution_id
        assert duplicate_context.execution_id == execution_id
        assert [event.execution_id for event in recorder.starts] == [execution_id, execution_id]
        assert [event.execution_id for event in recorder.terminals] == [execution_id, execution_id]
        assert [event.invocation_id for event in recorder.starts] == [
            event.invocation_id for event in recorder.terminals
        ]

    asyncio.run(run())


def test_scope_must_match_the_current_capability_and_principal_before_claiming() -> None:
    async def run() -> None:
        effects = 0

        def capture() -> str:
            nonlocal effects
            effects += 1
            return "captured"

        plan = plan_for(capture)
        store = InMemoryIdempotencyStore()
        wrong_capability = context_for(
            plan,
            store,
            scope_capability=CapabilityId.parse("orders.capture"),
        )
        wrong_principal = context_for(plan, store, scope_principal="customer-2")

        assert isinstance(await invoke_result(plan, wrong_capability), Failure)
        assert isinstance(await invoke_result(plan, wrong_principal), Failure)
        assert effects == 0
        assert (
            await store.lookup(IdempotencyScope(CAPTURE, "customer-1", "capture-1", b"capture-a"))
            is None
        )

    asyncio.run(run())


def test_store_failure_fails_closed_before_handler_work() -> None:
    class BrokenStore(InMemoryIdempotencyStore):
        async def claim(self, scope: IdempotencyScope, *, lease_ttl: float) -> NoReturn:
            raise IdempotencyStorageError("unavailable")

    async def run() -> None:
        effects = 0

        def capture() -> str:
            nonlocal effects
            effects += 1
            return "captured"

        plan = plan_for(capture)
        result = await invoke_result(plan, context_for(plan, BrokenStore()))

        assert result == Failure(FailureCode.UNAVAILABLE, "idempotency storage is unavailable")
        assert effects == 0

    asyncio.run(run())


@pytest.mark.parametrize("declared", [Idempotency.NO, Idempotency.UNKNOWN])
def test_non_idempotent_declarations_reject_an_explicit_reuse_option(declared: Idempotency) -> None:
    async def run() -> None:
        effects = 0

        def capture() -> str:
            nonlocal effects
            effects += 1
            return "captured"

        plan = plan_for(capture, idempotency=declared)
        result = await invoke_result(plan, context_for(plan, InMemoryIdempotencyStore()))

        assert result == Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")
        assert effects == 0

    asyncio.run(run())
