import asyncio
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


class MockHook(TelemetryHook):
    def __init__(self):
        self.starts = []
        self.terminals = []

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.starts.append(event)

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        self.terminals.append(event)


class FailingHook(TelemetryHook):
    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        raise ValueError("Start failed")

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        raise ValueError("Terminal failed")


def define(handler: Any) -> CapabilityDefinition:
    return CapabilityDefinition.declare(
        id=CapabilityId.parse("tests.test_cap"),
        handler=handler,
    )


def context_for(
    plan: ExecutionPlan,
    registry: DIRegistry,
    tracking_id: str | None = None,
    deadline: float | None = None,
) -> ExecutionContext:
    metadata = {}
    if tracking_id:
        metadata["tracking_id"] = tracking_id
    invocation = Invocation(
        capability_id=plan.definition.id,
        payload={},
        metadata=metadata,
        deadline=deadline,
    )
    return ExecutionContext(invocation=invocation, di_container=DIContainer(registry))


def test_telemetry_emits_success_outcome() -> None:
    async def run_test() -> None:
        registry = DIRegistry()

        def dummy() -> str:
            return "ok"

        hook1 = MockHook()
        hook2 = MockHook()
        plan = ExecutionPlan.compile(define(dummy), registry, hooks=[hook1, hook2])
        context = context_for(plan, registry, tracking_id="tr-123")

        await invoke(plan, context)

        assert len(hook1.starts) == 1
        assert len(hook1.terminals) == 1
        assert len(hook2.starts) == 1
        assert len(hook2.terminals) == 1

        assert hook1.starts[0].capability_id == plan.definition.id
        assert hook1.starts[0].tracking_id == "tr-123"

        assert hook1.terminals[0].capability_id == plan.definition.id
        assert hook1.terminals[0].tracking_id == "tr-123"
        assert hook1.terminals[0].outcome == "success"
        assert hook1.terminals[0].duration_ns > 0

    asyncio.run(run_test())


def test_telemetry_emits_failure_outcome_on_exception() -> None:
    async def run_test() -> None:
        registry = DIRegistry()

        def dummy() -> str:
            raise ValueError("boom")

        hook = MockHook()
        plan = ExecutionPlan.compile(define(dummy), registry, hooks=[hook])
        context = context_for(plan, registry)

        with pytest.raises(ValueError):
            await invoke(plan, context)

        assert hook.terminals[0].outcome == "failure"

    asyncio.run(run_test())


def test_telemetry_emits_timeout_outcome() -> None:
    async def run_test() -> None:
        registry = DIRegistry()

        async def dummy() -> None:
            await asyncio.Event().wait()

        hook = MockHook()
        plan = ExecutionPlan.compile(define(dummy), registry, hooks=[hook])
        # Instant timeout
        context = context_for(plan, registry, deadline=asyncio.get_running_loop().time())

        with pytest.raises(TimeoutError):
            await invoke(plan, context)

        assert hook.terminals[0].outcome == "timeout"

    asyncio.run(run_test())


def test_telemetry_emits_cancellation_outcome() -> None:
    async def run_test() -> None:
        registry = DIRegistry()
        started = asyncio.Event()

        async def dummy() -> None:
            started.set()
            await asyncio.Event().wait()

        hook = MockHook()
        plan = ExecutionPlan.compile(define(dummy), registry, hooks=[hook])
        context = context_for(plan, registry)

        task = asyncio.create_task(invoke(plan, context))
        await started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert hook.terminals[0].outcome == "cancellation"

    asyncio.run(run_test())


def test_telemetry_hook_failures_are_isolated() -> None:
    async def run_test() -> None:
        registry = DIRegistry()

        def dummy() -> str:
            return "ok"

        bad_hook = FailingHook()
        good_hook = MockHook()

        plan = ExecutionPlan.compile(define(dummy), registry, hooks=[bad_hook, good_hook])
        context = context_for(plan, registry)

        result = await invoke(plan, context)
        assert result == "ok"

        assert len(good_hook.starts) == 1
        assert len(good_hook.terminals) == 1

    asyncio.run(run_test())
