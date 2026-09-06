"""E9.6: skipping telemetry work for an unobserved invocation changes nothing.

`invoke` no longer builds a lifecycle event pair when `plan.hooks` is empty,
because nothing could receive it. These tests hold the observable behaviour
still, so the optimization stays an optimization: the hooked path must deliver
exactly what it delivered before, and the unhooked path must differ only by the
work nobody can see. See ADR 0058.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from agnara.capability.definition import CapabilityDefinition
from agnara.capability.identity import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution.context import ExecutionContext
from agnara.execution.invocation import Invocation
from agnara.execution.plan import ExecutionPlan
from agnara.execution.runtime import invoke, invoke_result
from agnara.execution.telemetry import (
    InvocationStartEvent,
    InvocationTerminalEvent,
    TelemetryHook,
)

CAPABILITY = CapabilityId.parse("tests.unobserved")


class RecordingHook(TelemetryHook):
    def __init__(self) -> None:
        self.starts: list[InvocationStartEvent] = []
        self.terminals: list[InvocationTerminalEvent] = []

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.starts.append(event)

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        self.terminals.append(event)


def plan_for(hooks: list[Any], registry: DIRegistry, handler: Any = None) -> ExecutionPlan:
    definition = CapabilityDefinition.declare(
        id=CAPABILITY,
        handler=handler or (lambda: "ok"),
    )
    return ExecutionPlan.compile(definition, registry, hooks=hooks)


def context_for(plan: ExecutionPlan, registry: DIRegistry) -> ExecutionContext:
    return ExecutionContext(
        Invocation(capability_id=plan.definition.id, payload={}, metadata={}),
        DIContainer(registry),
        tracking_id="req-1",
    )


def test_an_unobserved_invocation_returns_the_same_value() -> None:
    registry = DIRegistry()
    plan = plan_for([], registry)

    assert asyncio.run(invoke(plan, context_for(plan, registry))) == "ok"


def test_an_unobserved_invocation_generates_no_identity() -> None:
    """The saving is real, not a reordering: uuid4 is not called at all."""
    registry = DIRegistry()
    plan = plan_for([], registry)

    with patch("agnara.execution.runtime.uuid4") as generator:
        asyncio.run(invoke(plan, context_for(plan, registry)))

    generator.assert_not_called()


def test_an_observed_invocation_still_generates_one_identity() -> None:
    registry = DIRegistry()
    hook = RecordingHook()
    plan = plan_for([hook], registry)

    with patch("agnara.execution.runtime.uuid4", wraps=__import__("uuid").uuid4) as generator:
        asyncio.run(invoke(plan, context_for(plan, registry)))

    assert generator.call_count == 1
    assert hook.starts[0].invocation_id == hook.terminals[0].invocation_id


def test_an_unobserved_invocation_reads_no_tracking_id() -> None:
    """Resolving a tracking ID is observer-only work too."""
    registry = DIRegistry()
    plan = plan_for([], registry)

    with patch("agnara.execution.runtime._tracking_id") as resolve:
        asyncio.run(invoke(plan, context_for(plan, registry)))

    resolve.assert_not_called()


def test_an_unobserved_invocation_reads_no_clock() -> None:
    registry = DIRegistry()
    plan = plan_for([], registry)

    with patch("agnara.execution.runtime.time.monotonic_ns") as clock:
        asyncio.run(invoke(plan, context_for(plan, registry)))

    clock.assert_not_called()


@pytest.mark.parametrize("outcome", ["success", "failure", "timeout", "cancellation"])
def test_the_observed_path_delivers_the_same_events_for_every_outcome(outcome: str) -> None:
    """Guarding the unhooked path must not alter the hooked one."""
    registry = DIRegistry()
    hook = RecordingHook()

    async def handler() -> str:
        if outcome == "failure":
            raise ValueError("boom")
        if outcome == "timeout":
            await asyncio.sleep(60)
        if outcome == "cancellation":
            raise asyncio.CancelledError
        return "ok"

    async def run() -> None:
        plan = plan_for([hook], registry, handler)
        deadline = None
        if outcome == "timeout":
            deadline = asyncio.get_running_loop().time() + 0.01
        context = ExecutionContext(
            Invocation(
                capability_id=plan.definition.id,
                payload={},
                metadata={},
                deadline=deadline,
            ),
            DIContainer(registry),
            tracking_id="req-1",
        )
        if outcome == "success":
            assert await invoke(plan, context) == "ok"
            return
        with pytest.raises((ValueError, TimeoutError, asyncio.CancelledError)):
            await invoke(plan, context)

    asyncio.run(run())

    (start,) = hook.starts
    (terminal,) = hook.terminals
    assert start.capability_id == CAPABILITY
    assert start.tracking_id == "req-1"
    assert start.invocation_id
    assert terminal.capability_id == CAPABILITY
    assert terminal.tracking_id == "req-1"
    assert terminal.invocation_id == start.invocation_id
    assert terminal.outcome == outcome
    assert terminal.duration_ns > 0


def test_an_unobserved_failure_still_raises_and_cleans_up() -> None:
    """The guard is in a finally block; a raising handler must not change that."""
    registry = DIRegistry()

    def handler() -> str:
        raise ValueError("boom")

    plan = plan_for([], registry, handler)

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(invoke(plan, context_for(plan, registry)))


def test_an_unobserved_invocation_still_produces_a_canonical_result() -> None:
    registry = DIRegistry()

    def handler() -> str:
        raise ValueError("boom")

    plan = plan_for([], registry, handler)
    result = asyncio.run(invoke_result(plan, context_for(plan, registry)))

    assert result.__class__.__name__ == "Failure"


def test_adding_a_hook_to_a_second_plan_does_not_silence_the_first() -> None:
    """One plan's emptiness must not be cached onto another."""
    registry = DIRegistry()
    hook = RecordingHook()
    unobserved = plan_for([], registry)
    observed = plan_for([hook], registry)

    async def run() -> None:
        await invoke(unobserved, context_for(unobserved, registry))
        await invoke(observed, context_for(observed, registry))
        await invoke(unobserved, context_for(unobserved, registry))

    asyncio.run(run())

    assert len(hook.starts) == 1
    assert len(hook.terminals) == 1
