"""ADR 0087 runtime execution-identity contract."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from agnara.capability.definition import CapabilityDefinition
from agnara.capability.identity import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.errors import DefinitionError
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    InvocationStartEvent,
    InvocationTerminalEvent,
    StreamInterrupted,
    TelemetryHook,
    invoke_result,
    open_stream,
)

CAPABILITY = CapabilityId.parse("tests.execution_identity")


class Recorder(TelemetryHook):
    def __init__(self) -> None:
        self.starts: list[InvocationStartEvent] = []
        self.terminals: list[InvocationTerminalEvent] = []

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.starts.append(event)

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        self.terminals.append(event)


def plan_for(
    handler: Any, registry: DIRegistry, hooks: tuple[TelemetryHook, ...] = ()
) -> ExecutionPlan:
    return ExecutionPlan.compile(
        CapabilityDefinition.declare(id=CAPABILITY, handler=handler), registry, hooks=hooks
    )


def context_for(
    plan: ExecutionPlan,
    registry: DIRegistry,
    *,
    metadata: dict[str, Any] | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        Invocation(plan.definition.id, {}, {} if metadata is None else metadata),
        DIContainer(registry),
    )


def test_generated_execution_id_is_unique_and_an_opaque_uuid_token() -> None:
    registry = DIRegistry()
    plan = plan_for(lambda: "ok", registry)

    contexts = [context_for(plan, registry) for _ in range(200)]
    identities = {context.execution_id for context in contexts}

    assert len(identities) == 200
    assert all(len(identity) == 32 and int(identity, 16) >= 0 for identity in identities)
    with pytest.raises(AttributeError):
        object.__setattr__(contexts[0], "execution_id", "rewritten")


def test_one_execution_context_retains_its_identity_but_invocation_ids_remain_attempt_unique() -> (
    None
):
    async def run() -> None:
        registry = DIRegistry()
        recorder = Recorder()
        plan = plan_for(lambda: "ok", registry, (recorder,))
        context = context_for(plan, registry)
        execution_id = context.execution_id

        first = await invoke_result(plan, context)
        second = await invoke_result(plan, context)

        assert first.execution_id == second.execution_id == execution_id
        assert [event.execution_id for event in recorder.starts] == [execution_id] * 2
        assert [event.execution_id for event in recorder.terminals] == [execution_id] * 2
        assert recorder.starts[0].invocation_id != recorder.starts[1].invocation_id
        assert [event.invocation_id for event in recorder.terminals] == [
            event.invocation_id for event in recorder.starts
        ]

    asyncio.run(run())


@pytest.mark.parametrize("caller_value", [None, "", "has a space", "café", "line\nbreak"])
def test_caller_supplied_execution_identity_is_rejected_before_handler_side_effects(
    caller_value: object,
) -> None:
    registry = DIRegistry()
    called = False

    def handler() -> None:
        nonlocal called
        called = True

    plan = plan_for(handler, registry)

    with pytest.raises(DefinitionError, match="must not be supplied through invocation metadata"):
        context_for(plan, registry, metadata={"execution_id": caller_value})

    assert not called


def test_concurrent_contexts_keep_execution_identity_task_local() -> None:
    async def handler(context: ExecutionContext) -> str:
        await asyncio.sleep(0)
        return context.execution_id

    async def run() -> None:
        registry = DIRegistry()
        plan = plan_for(handler, registry)

        async def one() -> tuple[str, str | None]:
            context = context_for(plan, registry)
            outcome = await invoke_result(plan, context)
            return context.execution_id, outcome.execution_id

        pairs = await asyncio.gather(*(one() for _ in range(50)))
        assert len({context_id for context_id, _ in pairs}) == 50
        assert all(context_id == outcome_id for context_id, outcome_id in pairs)

    asyncio.run(run())


def test_nested_contexts_keep_their_own_execution_identity() -> None:
    async def run() -> None:
        registry = DIRegistry()

        def inner_handler(context: ExecutionContext) -> str:
            return context.execution_id

        inner_definition = CapabilityDefinition.declare(
            id=CapabilityId.parse("tests.nested_identity_inner"),
            handler=inner_handler,
        )
        inner_plan = ExecutionPlan.compile(inner_definition, registry)
        inner_context = ExecutionContext(
            Invocation(inner_definition.id, {}, {}),
            DIContainer(registry),
        )

        async def outer(context: ExecutionContext) -> tuple[str, str | None]:
            inner = await invoke_result(inner_plan, inner_context)
            return context.execution_id, inner.execution_id

        outer_plan = plan_for(outer, registry)
        outer_context = context_for(outer_plan, registry)

        outcome = await invoke_result(outer_plan, outer_context)

        assert not isinstance(outcome, Failure)
        assert outcome.value == (outer_context.execution_id, inner_context.execution_id)
        assert outcome.execution_id == outer_context.execution_id
        assert outer_context.execution_id != inner_context.execution_id

    asyncio.run(run())


def test_failure_and_cancellation_keep_execution_identity_in_safe_outcomes_and_telemetry() -> None:
    async def run() -> None:
        registry = DIRegistry()
        failure_plan = plan_for(lambda: (_ for _ in ()).throw(RuntimeError("secret")), registry)
        failure_context = context_for(failure_plan, registry)

        failure = await invoke_result(failure_plan, failure_context)

        assert isinstance(failure, Failure)
        assert failure.execution_id == failure_context.execution_id
        assert failure.message == "capability invocation failed"

        recorder = Recorder()

        async def cancelled() -> None:
            raise asyncio.CancelledError

        cancellation_plan = plan_for(cancelled, registry, (recorder,))
        cancellation_context = context_for(cancellation_plan, registry)
        with pytest.raises(asyncio.CancelledError):
            await invoke_result(cancellation_plan, cancellation_context)

        assert recorder.starts[0].execution_id == cancellation_context.execution_id
        assert recorder.terminals[0].execution_id == cancellation_context.execution_id
        assert recorder.terminals[0].outcome == "cancellation"

    asyncio.run(run())


def test_stream_and_late_failure_carry_the_execution_identity() -> None:
    async def rows(context: ExecutionContext) -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("secret")

    async def run() -> None:
        registry = DIRegistry()
        recorder = Recorder()
        definition = CapabilityDefinition.declare(id=CAPABILITY, handler=rows, streaming=True)
        plan = ExecutionPlan.compile(definition, registry, hooks=(recorder,))
        context = context_for(plan, registry)

        async with open_stream(plan, context) as stream:
            assert stream.execution_id == context.execution_id
            assert await anext(stream) == 1
            with pytest.raises(StreamInterrupted) as raised:
                await anext(stream)

        assert raised.value.failure.execution_id == context.execution_id
        assert recorder.starts[0].execution_id == context.execution_id
        assert recorder.terminals[0].execution_id == context.execution_id

    asyncio.run(run())
