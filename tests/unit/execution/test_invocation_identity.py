"""E9.3 contract: the runtime, not the caller, identifies an invocation.

ADR 0023 states a caller ``tracking_id`` is neither unique nor a safe storage
key, which is why ADR 0054 deferred spans. These tests pin the replacement:
one runtime-generated ``invocation_id`` shared by a start event and its
terminal event, and shared by nothing else.
"""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from agnara.capability.definition import CapabilityDefinition
from agnara.capability.identity import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution.context import ExecutionContext
from agnara.execution.invocation import Invocation
from agnara.execution.plan import ExecutionPlan
from agnara.execution.runtime import invoke
from agnara.execution.telemetry import (
    InvocationStartEvent,
    InvocationTerminalEvent,
    TelemetryHook,
)

CAPABILITY = CapabilityId.parse("tests.identity_cap")


class RecordingHook(TelemetryHook):
    def __init__(self) -> None:
        self.starts: list[InvocationStartEvent] = []
        self.terminals: list[InvocationTerminalEvent] = []

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.starts.append(event)

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        self.terminals.append(event)


class StartFailingHook(RecordingHook):
    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        super().on_invocation_start(event)
        raise ValueError("start observer failed")


def plan_for(handler: Any, hooks: list[Any], registry: DIRegistry) -> ExecutionPlan:
    definition = CapabilityDefinition.declare(id=CAPABILITY, handler=handler)
    return ExecutionPlan.compile(definition, registry, hooks=hooks)


def context_for(
    plan: ExecutionPlan,
    registry: DIRegistry,
    tracking_id: str | None = None,
    deadline: float | None = None,
) -> ExecutionContext:
    metadata: dict[str, Any] = {} if tracking_id is None else {"tracking_id": tracking_id}
    return ExecutionContext(
        invocation=Invocation(
            capability_id=plan.definition.id,
            payload={},
            metadata=metadata,
            deadline=deadline,
        ),
        di_container=DIContainer(registry),
    )


def test_start_and_terminal_share_one_identity() -> None:
    async def run() -> None:
        registry = DIRegistry()
        hook = RecordingHook()
        plan = plan_for(lambda: "ok", [hook], registry)

        await invoke(plan, context_for(plan, registry, tracking_id="tr-1"))

        identity = hook.starts[0].invocation_id
        assert isinstance(identity, str)
        assert identity
        assert hook.terminals[0].invocation_id == identity

    asyncio.run(run())


def test_every_invocation_of_one_plan_receives_a_distinct_identity() -> None:
    """Sequential reuse of a compiled plan must not reuse an identity."""

    async def run() -> None:
        registry = DIRegistry()
        hook = RecordingHook()
        plan = plan_for(lambda: "ok", [hook], registry)

        for _ in range(200):
            await invoke(plan, context_for(plan, registry, tracking_id="always-the-same"))

        identities = [event.invocation_id for event in hook.starts]
        assert len(set(identities)) == 200
        assert [event.invocation_id for event in hook.terminals] == identities

    asyncio.run(run())


@pytest.mark.parametrize("tracking_id", [None, "", "tr-1", "0" * 32])
def test_identity_is_never_derived_from_caller_metadata(tracking_id: str | None) -> None:
    """A caller must not be able to choose, guess or collide with an identity."""

    async def run() -> None:
        registry = DIRegistry()
        hook = RecordingHook()
        plan = plan_for(lambda: "ok", [hook], registry)

        await invoke(plan, context_for(plan, registry, tracking_id=tracking_id))

        start = hook.starts[0]
        assert start.tracking_id == tracking_id
        assert start.invocation_id != tracking_id
        assert start.invocation_id

    asyncio.run(run())


def test_all_hooks_on_one_plan_observe_the_same_identity() -> None:
    async def run() -> None:
        registry = DIRegistry()
        first, second = RecordingHook(), RecordingHook()
        plan = plan_for(lambda: "ok", [first, second], registry)

        await invoke(plan, context_for(plan, registry))

        assert first.starts[0].invocation_id == second.starts[0].invocation_id
        assert first.terminals[0].invocation_id == second.terminals[0].invocation_id

    asyncio.run(run())


def test_nested_invocations_receive_distinct_identities() -> None:
    """An inner invocation must not overwrite the enclosing one's state."""

    async def run() -> None:
        registry = DIRegistry()
        hook = RecordingHook()
        inner_definition = CapabilityDefinition.declare(
            id=CapabilityId.parse("tests.inner_cap"),
            handler=lambda: "inner",
        )
        inner = ExecutionPlan.compile(inner_definition, registry, hooks=[hook])
        inner_context = ExecutionContext(
            invocation=Invocation(capability_id=inner.definition.id, payload={}, metadata={}),
            di_container=DIContainer(registry),
        )

        async def outer_handler() -> str:
            return str(await invoke(inner, inner_context))

        outer = plan_for(outer_handler, [hook], registry)
        await invoke(outer, context_for(outer, registry))

        outer_id, inner_id = (event.invocation_id for event in hook.starts)
        assert outer_id != inner_id
        # The inner invocation terminates first, inside the outer one.
        assert [event.invocation_id for event in hook.terminals] == [inner_id, outer_id]

    asyncio.run(run())


def test_concurrent_invocations_receive_distinct_identities() -> None:
    async def run() -> None:
        registry = DIRegistry()
        hook = RecordingHook()

        async def handler() -> str:
            await asyncio.sleep(0)
            return "ok"

        plan = plan_for(handler, [hook], registry)
        await asyncio.gather(
            *(invoke(plan, context_for(plan, registry, tracking_id="shared")) for _ in range(50))
        )

        starts = {event.invocation_id for event in hook.starts}
        terminals = {event.invocation_id for event in hook.terminals}
        assert len(starts) == 50
        assert starts == terminals

    asyncio.run(run())


def test_a_suppressed_start_still_receives_its_terminal_identity() -> None:
    """An observer that failed at start must be able to recognize the orphan."""

    async def run() -> None:
        registry = DIRegistry()
        hook = StartFailingHook()
        plan = plan_for(lambda: "ok", [hook], registry)

        await invoke(plan, context_for(plan, registry))

        assert hook.terminals[0].invocation_id == hook.starts[0].invocation_id

    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["failure", "timeout", "cancellation"])
def test_identity_survives_every_non_success_outcome(outcome: str) -> None:
    async def run() -> None:
        registry = DIRegistry()
        hook = RecordingHook()

        async def handler() -> str:
            if outcome == "failure":
                raise ValueError("boom")
            if outcome == "timeout":
                await asyncio.sleep(60)
            raise asyncio.CancelledError

        plan = plan_for(handler, [hook], registry)
        deadline = None
        if outcome == "timeout":
            deadline = asyncio.get_running_loop().time() + 0.01
        context = context_for(plan, registry, deadline=deadline)

        with pytest.raises((ValueError, TimeoutError, asyncio.CancelledError)):
            await invoke(plan, context)

        assert hook.terminals[0].outcome == outcome
        assert hook.terminals[0].invocation_id == hook.starts[0].invocation_id

    asyncio.run(run())


@pytest.mark.parametrize(
    "event",
    [
        InvocationStartEvent(CAPABILITY, None, "abc"),
        InvocationTerminalEvent(CAPABILITY, None, 1, "success", "abc"),
    ],
)
def test_identity_cannot_be_reassigned_on_a_delivered_event(event: Any) -> None:
    with pytest.raises(FrozenInstanceError):
        event.invocation_id = "rewritten"
