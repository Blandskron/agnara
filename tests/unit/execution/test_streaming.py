"""The kernel streaming contract decided by ADR 0084.

RFC 0009 section 6 lists the scenarios an answer has to be able to state
expected observations for. Those scenarios are the spine of this module, and
each one is a test rather than a paragraph, because the RFC's whole complaint
about "let the first adapter decide" is that nobody could check the decision.

Everything here is protocol-neutral on purpose: no test in this file knows
that HTTP, MCP or A2A exist, and the kernel it exercises must not either.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest

from agnara import DefinitionError, InvocationError, PolicyDeniedError
from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIContainer, DIRegistry, provider
from agnara.execution import (
    CapabilityStream,
    ExecutionContext,
    ExecutionPlan,
    FailureCode,
    Invocation,
    InvocationStartEvent,
    InvocationTerminalEvent,
    StreamInterrupted,
    StreamTerminal,
    Success,
    invoke,
    invoke_result,
    open_stream,
)
from agnara.policy import PolicyFailure, PolicyResult

CAPABILITY = CapabilityId("reports", "rows")


class Cursor:
    """Stands in for the invocation-scoped database cursor RFC 0009 names."""

    def __init__(self) -> None:
        self.closed = False


#: Teardown observed by the tests. A provider is the only place that can say
#: whether the invocation scope really outlived the producer.
TEARDOWN: list[str] = []


@provider()
async def provide_cursor() -> AsyncIterator[Cursor]:
    cursor = Cursor()
    try:
        yield cursor
    finally:
        cursor.closed = True
        TEARDOWN.append("cursor")


@pytest.fixture(autouse=True)
def _clear_teardown() -> Iterator[None]:
    TEARDOWN.clear()
    yield
    TEARDOWN.clear()


def definition(handler: Callable[..., Any], *, streaming: bool = True) -> CapabilityDefinition:
    return CapabilityDefinition(id=CAPABILITY, handler=handler, streaming=streaming)


def plan_for(
    handler: Callable[..., Any],
    registry: DIRegistry | None = None,
    *,
    streaming: bool = True,
    hooks: tuple[Any, ...] = (),
    policies: tuple[Any, ...] = (),
) -> ExecutionPlan:
    return ExecutionPlan.compile(
        CapabilityDefinition(
            id=CAPABILITY,
            handler=handler,
            streaming=streaming,
            policies=policies,
        ),
        registry if registry is not None else DIRegistry(),
        hooks=hooks,
    )


def context_for(
    plan: ExecutionPlan,
    registry: DIRegistry,
    payload: dict[str, Any] | None = None,
    *,
    deadline: float | None = None,
) -> ExecutionContext:
    invocation = Invocation(
        capability_id=plan.definition.id,
        payload=payload or {},
        metadata={},
        deadline=deadline,
    )
    return ExecutionContext(invocation, DIContainer(registry))


# ---------------------------------------------------------------------------
# D1 -- declaration and shape are held to each other at compile time
# ---------------------------------------------------------------------------


def test_an_async_generator_handler_nobody_declared_is_rejected() -> None:
    """The rejection that keeps a producer out of the complete-result boundary.

    Without it `invoke_result` would wrap the generator object in `Success`
    and hand back a producer with no owner -- silently, and only at runtime.
    """

    async def rows() -> AsyncIterator[int]:
        yield 1

    with pytest.raises(DefinitionError, match="does not declare streaming=True"):
        ExecutionPlan.compile(definition(rows, streaming=False), DIRegistry())


def test_a_streaming_declaration_over_an_ordinary_handler_is_rejected() -> None:
    async def rows() -> list[int]:
        return [1]

    with pytest.raises(DefinitionError, match="not an async generator function"):
        ExecutionPlan.compile(definition(rows), DIRegistry())


def test_a_callable_object_is_judged_by_what_it_does() -> None:
    """A handler that is an instance is inspected through its ``__call__``."""

    class Rows:
        async def __call__(self) -> AsyncIterator[int]:
            yield 1

    with pytest.raises(DefinitionError, match="does not declare streaming=True"):
        ExecutionPlan.compile(definition(Rows(), streaming=False), DIRegistry())

    assert ExecutionPlan.compile(definition(Rows()), DIRegistry()).streaming is True


def test_streaming_must_be_a_bool() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1

    with pytest.raises(DefinitionError, match="streaming must be a bool"):
        CapabilityDefinition(id=CAPABILITY, handler=rows, streaming="yes")  # ty: ignore[invalid-argument-type]


def test_a_non_streaming_capability_keeps_the_existing_boundary() -> None:
    """RFC 0009 section 6: nothing about complete results changes."""

    async def rows() -> list[int]:
        return [1, 2]

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry, streaming=False)
        context = context_for(plan, registry)

        result = await invoke_result(plan, context)

        assert isinstance(result, Success)
        assert result.value == [1, 2]
        assert plan.streaming is False
        await context.di_container.aclose()

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# D3 -- the boundary owns the stream, one-shot
# ---------------------------------------------------------------------------


def test_a_stream_that_is_never_opened_acquires_nothing() -> None:
    """RFC 0009 Q3 asks this outright: what if a caller never iterates?"""

    async def rows(cursor: Cursor) -> AsyncIterator[int]:
        yield 1

    registry = DIRegistry()
    registry.bind(Cursor, provide_cursor)
    plan = plan_for(rows, registry)
    context = context_for(plan, registry)

    stream = open_stream(plan, context)

    assert isinstance(stream, CapabilityStream)
    assert stream.terminal is None
    assert stream.units_emitted == 0
    assert TEARDOWN == []


def test_a_stream_is_one_shot() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)
        stream = open_stream(plan, context)

        async with stream:
            pass

        with pytest.raises(InvocationError, match="one-shot"):
            await stream.__aenter__()

        await context.di_container.aclose()

    asyncio.run(run_test())


def test_iterating_before_opening_is_refused() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry)
        stream = open_stream(plan, context_for(plan, registry))

        with pytest.raises(InvocationError, match="iterated before it was opened"):
            await anext(stream)

    asyncio.run(run_test())


def test_the_complete_result_boundary_refuses_a_streaming_plan() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)

        with pytest.raises(InvocationError, match="use open_stream"):
            await invoke(plan, context)

        await context.di_container.aclose()

    asyncio.run(run_test())


def test_open_stream_refuses_a_complete_result_plan() -> None:
    async def rows() -> int:
        return 1

    registry = DIRegistry()
    plan = plan_for(rows, registry, streaming=False)

    with pytest.raises(InvocationError, match="not declared streaming"):
        open_stream(plan, context_for(plan, registry))


def test_open_stream_refuses_a_context_for_another_capability() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1

    registry = DIRegistry()
    plan = plan_for(rows, registry)
    invocation = Invocation(
        capability_id=CapabilityId("reports", "other"),
        payload={},
        metadata={},
    )
    context = ExecutionContext(invocation, DIContainer(registry))

    with pytest.raises(InvocationError, match="but the compiled plan is for"):
        open_stream(plan, context)


# ---------------------------------------------------------------------------
# RFC 0009 section 6 -- normal completion over an invocation-scoped resource
# ---------------------------------------------------------------------------


def test_a_generator_over_an_invocation_scoped_cursor_completes() -> None:
    seen: list[Cursor] = []

    async def rows(cursor: Cursor) -> AsyncIterator[int]:
        seen.append(cursor)
        for value in (1, 2, 3):
            yield value

    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Cursor, provide_cursor)
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)

        async with open_stream(plan, context) as stream:
            assert TEARDOWN == [], "the scope must outlive the producer, not precede it"
            collected = [unit async for unit in stream]

            assert collected == [1, 2, 3]
            assert stream.terminal is StreamTerminal.COMPLETED
            assert stream.units_emitted == 3

        assert TEARDOWN == ["cursor"]
        assert seen[0].closed is True
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_an_empty_successful_stream_completes_with_no_units() -> None:
    """Distinct in kind from failing before first output, which never opens."""

    async def rows() -> AsyncIterator[int]:
        return
        yield  # pragma: no cover - unreachable, declares the async generator

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)

        async with open_stream(plan, context) as stream:
            assert [unit async for unit in stream] == []
            assert stream.terminal is StreamTerminal.COMPLETED
            assert stream.units_emitted == 0

        await context.di_container.aclose()

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# D4 -- pull-based demand, with nothing buffered anywhere
# ---------------------------------------------------------------------------


def test_a_slow_consumer_slows_the_producer() -> None:
    """RFC 0009 section 6: one unit at a time, without unbounded buffering.

    The producer records how far it has run. If the kernel prefetched or
    buffered, production would run ahead of consumption and this would fail.
    """
    produced: list[int] = []

    async def rows() -> AsyncIterator[int]:
        for value in range(5):
            produced.append(value)
            yield value

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)

        async with open_stream(plan, context) as stream:
            assert produced == [], "nothing may be produced before the first pull"
            consumed = []
            async for unit in stream:
                consumed.append(unit)
                await asyncio.sleep(0)
                assert produced == consumed, "the producer ran ahead of demand"

        await context.di_container.aclose()

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# RFC 0009 constraint 4 -- policy and validation are pre-output
# ---------------------------------------------------------------------------


def test_policy_denial_happens_before_the_producer_starts() -> None:
    started = False

    async def rows() -> AsyncIterator[int]:
        nonlocal started
        started = True
        yield 1

    class Deny:
        async def evaluate(self, context: ExecutionContext) -> PolicyResult:
            return PolicyFailure("nope")

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry, policies=(Deny(),))
        context = context_for(plan, registry)

        with pytest.raises(PolicyDeniedError):
            async with open_stream(plan, context):
                pass  # pragma: no cover - entering is what raises

        assert started is False
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_input_validation_happens_before_the_producer_starts() -> None:
    started = False

    async def rows(limit: int) -> AsyncIterator[int]:
        nonlocal started
        started = True
        yield limit

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry)
        context = context_for(plan, registry, {"limit": "not an int"})

        with pytest.raises(Exception, match="int"):
            async with open_stream(plan, context):
                pass  # pragma: no cover - entering is what raises

        assert started is False
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_an_explicit_materializer_runs_after_policy_and_before_validation() -> None:
    order: list[str] = []

    async def rows(limit: int) -> AsyncIterator[int]:
        yield limit

    class Recording:
        async def evaluate(self, context: ExecutionContext) -> PolicyResult:
            order.append("policy")
            from agnara.policy import PolicySuccess

            return PolicySuccess()

    def materialize(schema: Any, value: object) -> object:
        order.append("materialize")
        return int(str(value))

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry, policies=(Recording(),))
        context = context_for(plan, registry, {"limit": "7"})

        async with open_stream(plan, context, input_materializer=materialize) as stream:
            assert [unit async for unit in stream] == [7]

        assert order == ["policy", "materialize"]
        await context.di_container.aclose()

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# D6 -- failure after output is never dressed up as a complete result
# ---------------------------------------------------------------------------


def test_a_producer_failure_after_output_is_interrupted_and_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RFC 0009 section 6: the exception must not leak, and must not pretend."""

    async def rows() -> AsyncIterator[int]:
        yield 1
        yield 2
        raise RuntimeError("connection string postgres://user:hunter2@db/prod")

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)

        with caplog.at_level(logging.ERROR, logger="agnara.execution"):
            async with open_stream(plan, context) as stream:
                assert await anext(stream) == 1
                assert await anext(stream) == 2

                with pytest.raises(StreamInterrupted) as raised:
                    await anext(stream)

            interruption = raised.value
            assert interruption.units_emitted == 2, "output already reached the consumer"
            assert interruption.failure.code is FailureCode.INTERNAL_FAILURE
            assert "hunter2" not in interruption.failure.message
            assert stream.terminal is StreamTerminal.INTERRUPTED

        assert "hunter2" not in caplog.text
        assert str(CAPABILITY) in caplog.text
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_a_producer_failing_on_the_first_pull_emitted_nothing() -> None:
    """Zero units is what tells an adapter it may still project the ordinary
    canonical failure. Any larger number means it must not.
    """

    async def rows() -> AsyncIterator[int]:
        raise RuntimeError("boom")
        yield  # pragma: no cover - unreachable, declares the async generator

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)

        async with open_stream(plan, context) as stream:
            with pytest.raises(StreamInterrupted) as raised:
                await anext(stream)

            assert raised.value.units_emitted == 0
            assert stream.terminal is StreamTerminal.INTERRUPTED

        await context.di_container.aclose()

    asyncio.run(run_test())


def test_a_producer_failure_still_tears_the_invocation_scope_down() -> None:
    async def rows(cursor: Cursor) -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("boom")

    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Cursor, provide_cursor)
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)

        async with open_stream(plan, context) as stream:
            assert await anext(stream) == 1
            with pytest.raises(StreamInterrupted):
                await anext(stream)

        assert TEARDOWN == ["cursor"]
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_iterating_past_a_terminal_state_reports_exhaustion() -> None:
    """`terminal` stays the authority on how the stream ended."""

    async def rows() -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("boom")

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)

        async with open_stream(plan, context) as stream:
            assert await anext(stream) == 1
            with pytest.raises(StreamInterrupted):
                await anext(stream)
            with pytest.raises(StopAsyncIteration):
                await anext(stream)

            assert stream.terminal is StreamTerminal.INTERRUPTED

        await context.di_container.aclose()

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# D5 -- deadline, cancellation and abandonment
# ---------------------------------------------------------------------------


def test_a_deadline_expiring_before_first_output_never_opens_the_stream() -> None:
    async def rows() -> AsyncIterator[int]:
        await asyncio.sleep(5)
        yield 1  # pragma: no cover - the deadline arrives first

    class Slow:
        async def evaluate(self, context: ExecutionContext) -> PolicyResult:
            await asyncio.sleep(5)
            from agnara.policy import PolicySuccess

            return PolicySuccess()  # pragma: no cover - the deadline arrives first

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry, policies=(Slow(),))
        loop = asyncio.get_running_loop()
        context = context_for(plan, registry, deadline=loop.time() + 0.01)
        stream = open_stream(plan, context)

        with pytest.raises(TimeoutError):
            await stream.__aenter__()

        assert stream.terminal is StreamTerminal.TIMED_OUT
        assert stream.units_emitted == 0
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_a_deadline_expiring_after_several_units_interrupts_the_stream() -> None:
    async def rows(cursor: Cursor) -> AsyncIterator[int]:
        yield 1
        yield 2
        await asyncio.sleep(5)
        yield 3  # pragma: no cover - the deadline arrives first

    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Cursor, provide_cursor)
        plan = plan_for(rows, registry)
        loop = asyncio.get_running_loop()
        context = context_for(plan, registry, deadline=loop.time() + 0.05)

        async with open_stream(plan, context) as stream:
            assert await anext(stream) == 1
            assert await anext(stream) == 2

            with pytest.raises(StreamInterrupted) as raised:
                await anext(stream)

            assert raised.value.failure.code is FailureCode.TIMEOUT
            assert raised.value.units_emitted == 2
            assert stream.terminal is StreamTerminal.TIMED_OUT

        assert TEARDOWN == ["cursor"]
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_cancellation_propagates_untouched_and_runs_cleanup() -> None:
    """RFC 0009 constraint 3: cancellation is control flow, not an outcome."""
    cleaned = False

    async def rows(cursor: Cursor) -> AsyncIterator[int]:
        nonlocal cleaned
        try:
            yield 1
            await asyncio.sleep(5)
            yield 2  # pragma: no cover - cancelled first
        finally:
            cleaned = True

    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Cursor, provide_cursor)
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)
        observed: list[StreamTerminal | None] = []

        async def consume() -> None:
            async with open_stream(plan, context) as stream:
                try:
                    assert await anext(stream) == 1
                    await anext(stream)
                finally:
                    observed.append(stream.terminal)

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.02)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert observed == [StreamTerminal.CANCELLED]
        assert cleaned is True
        assert TEARDOWN == ["cursor"]
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_a_consumer_that_stops_early_abandons_the_stream_and_leaves_nothing() -> None:
    """RFC 0009 section 6: no background task and no live provider afterwards."""
    cleaned = False

    async def rows(cursor: Cursor) -> AsyncIterator[int]:
        nonlocal cleaned
        try:
            for value in range(100):
                yield value
        finally:
            cleaned = True

    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Cursor, provide_cursor)
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)
        before = len(asyncio.all_tasks())

        async with open_stream(plan, context) as stream:
            assert await anext(stream) == 0
            assert await anext(stream) == 1

        assert stream.terminal is StreamTerminal.ABANDONED
        assert stream.units_emitted == 2
        assert cleaned is True
        assert TEARDOWN == ["cursor"]
        assert len(asyncio.all_tasks()) == before, "the kernel left a task running"
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_closing_twice_tears_down_once() -> None:
    async def rows(cursor: Cursor) -> AsyncIterator[int]:
        yield 1

    async def run_test() -> None:
        registry = DIRegistry()
        registry.bind(Cursor, provide_cursor)
        plan = plan_for(rows, registry)
        context = context_for(plan, registry)

        stream = open_stream(plan, context)
        async with stream:
            assert await anext(stream) == 1

        await stream.aclose()
        await stream.aclose()

        assert TEARDOWN == ["cursor"]
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_closing_a_stream_that_was_never_opened_is_harmless() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1

    async def run_test() -> None:
        registry = DIRegistry()
        plan = plan_for(rows, registry)
        stream = open_stream(plan, context_for(plan, registry))

        await stream.aclose()

        assert stream.terminal is None

    asyncio.run(run_test())


# ---------------------------------------------------------------------------
# D7 -- telemetry spans the whole stream lifetime
# ---------------------------------------------------------------------------


class Recorder:
    def __init__(self) -> None:
        self.started: list[InvocationStartEvent] = []
        self.terminal: list[InvocationTerminalEvent] = []

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.started.append(event)

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        self.terminal.append(event)


def test_telemetry_pairs_one_start_with_one_terminal_carrying_the_unit_count() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1
        yield 2

    async def run_test() -> None:
        recorder = Recorder()
        registry = DIRegistry()
        plan = plan_for(rows, registry, hooks=(recorder,))
        context = context_for(plan, registry)

        async with open_stream(plan, context) as stream:
            assert [unit async for unit in stream] == [1, 2]
            assert recorder.terminal == [], "the terminal event belongs to the close"

        [start] = recorder.started
        [terminal] = recorder.terminal
        assert terminal.invocation_id == start.invocation_id
        assert terminal.outcome == StreamTerminal.COMPLETED.value
        assert terminal.units == 2
        assert terminal.duration_ns > 0
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_a_complete_result_invocation_reports_no_unit_count() -> None:
    """``units`` is how an observer tells the two boundaries apart."""

    async def rows() -> int:
        return 1

    async def run_test() -> None:
        recorder = Recorder()
        registry = DIRegistry()
        plan = plan_for(rows, registry, streaming=False, hooks=(recorder,))
        context = context_for(plan, registry)

        await invoke_result(plan, context)

        [terminal] = recorder.terminal
        assert terminal.units is None
        assert terminal.outcome == "success"
        await context.di_container.aclose()

    asyncio.run(run_test())


def test_an_interrupted_stream_reports_its_terminal_classification() -> None:
    async def rows() -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("boom")

    async def run_test() -> None:
        recorder = Recorder()
        registry = DIRegistry()
        plan = plan_for(rows, registry, hooks=(recorder,))
        context = context_for(plan, registry)

        async with open_stream(plan, context) as stream:
            assert await anext(stream) == 1
            with pytest.raises(StreamInterrupted):
                await anext(stream)

        [terminal] = recorder.terminal
        assert terminal.outcome == StreamTerminal.INTERRUPTED.value
        assert terminal.units == 1
        await context.di_container.aclose()

    asyncio.run(run_test())
