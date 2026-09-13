"""The protocol-neutral streaming execution boundary (ADR 0084).

A streaming capability is an async generator that was declared as one. The
kernel owns opening it, pulling from it, closing it and releasing everything
it borrowed, and it does all of that without knowing that HTTP, MCP, A2A or an
event broker exist.

Three properties are the point of this module, and each is a decision rather
than an implementation detail:

* **Pull-based demand.** There is no queue, no prefetch and no internal task.
  A pull reaches the producer directly, so a slow consumer slows the producer
  and nothing accumulates anywhere (ADR 0084 D4).
* **One owner.** The stream is a one-shot async context manager. Closing it
  closes the producer first and then the invocation dependency scope, exactly
  once, on every path including cancellation (ADR 0084 D3, D7).
* **Honest terminal state.** Output that has reached a consumer cannot be
  taken back, so a failure after the first pull raises `StreamInterrupted`
  rather than a canonical `Failure` that would imply nothing happened
  (ADR 0084 D6).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from dataclasses import replace
from enum import StrEnum
from types import TracebackType
from typing import Any, Self
from uuid import uuid4

from agnara.errors import AgnaraError, InvocationError
from agnara.execution._outcome import classify
from agnara.execution._output import validate_output
from agnara.execution._preflight import bind_inputs, enforce_policies, tracking_id
from agnara.execution.context import ExecutionContext
from agnara.execution.plan import ExecutionPlan
from agnara.execution.result import Failure, FailureCode
from agnara.execution.telemetry import InvocationStartEvent, InvocationTerminalEvent
from agnara.schema import TypeSchema

__all__ = [
    "CapabilityStream",
    "StreamInterrupted",
    "StreamTerminal",
    "open_stream",
]


class StreamTerminal(StrEnum):
    """How a stream ended.

    A consumer cannot infer this from the absence of further units, which is
    the whole reason it is recorded: RFC 0009 constraint 8 requires normal
    completion, producer failure, deadline expiry and cancellation to be
    distinguishable without guessing.
    """

    COMPLETED = "completed"
    """The producer was exhausted normally."""

    INTERRUPTED = "interrupted"
    """The producer failed after iteration began."""

    CANCELLED = "cancelled"
    """Cancellation propagated through the stream."""

    TIMED_OUT = "timed_out"
    """The invocation deadline expired."""

    ABANDONED = "abandoned"
    """The owner closed the stream before the producer was exhausted."""


class StreamInterrupted(AgnaraError):
    """A stream failed after iteration had begun.

    This is deliberately not a canonical `Failure` returned from the boundary.
    Once any unit has reached a consumer, presenting a later error as though
    the invocation produced nothing is a lie the transport then has to repeat
    (RFC 0009 constraint 7).

    ``failure`` is classified and redacted by exactly the rules
    `invoke_result` applies, so an unexpected producer exception carries no
    message, path or traceback. ``units_emitted`` is how many units the
    consumer already received: zero means nothing was exposed and an adapter
    may still project the ordinary canonical failure, while any larger number
    means it must not.
    """

    def __init__(self, failure: Failure, units_emitted: int) -> None:
        super().__init__(failure.message)
        self.failure = failure
        self.units_emitted = units_emitted


def open_stream(
    plan: ExecutionPlan,
    context: ExecutionContext,
    *,
    input_materializer: Callable[[TypeSchema, object], object] | None = None,
) -> CapabilityStream:
    """Build the owned stream for a streaming capability, without starting it.

    Nothing is evaluated, resolved or acquired here. A caller that obtains a
    stream and never enters it has leaked nothing, which is the answer this
    boundary owes RFC 0009 Q3. Entering the returned object runs policy,
    validation and dependency construction; iterating it pulls units.

    Use it as the one-shot async context manager it is::

        async with open_stream(plan, context) as stream:
            async for unit in stream:
                ...

    ``input_materializer`` is the same explicit wire conversion
    `invoke_result` accepts (ADR 0077): a JSON transport passes
    ``materialize_json``, and it runs after policy and before strict
    validation. Direct Python consumption passes nothing and stays strict.

    Raises:
        TypeError: ``plan`` or ``context`` is of the wrong type.
        InvocationError: the plan is not a streaming capability, or the
            context targets a different capability than the plan compiles.
    """
    if not isinstance(plan, ExecutionPlan):
        raise TypeError(f"plan must be an ExecutionPlan, got {type(plan).__name__}")
    if not isinstance(context, ExecutionContext):
        raise TypeError(f"context must be an ExecutionContext, got {type(context).__name__}")
    if not plan.streaming:
        raise InvocationError(
            f"capability {plan.definition.id} is not declared streaming; use invoke_result()"
        )
    if context.invocation.capability_id != plan.definition.id:
        raise InvocationError(
            f"invocation targets {context.invocation.capability_id}, but the compiled plan is "
            f"for {plan.definition.id}"
        )
    return CapabilityStream(plan, context, input_materializer)


class CapabilityStream:
    """One owned, one-shot consumption of a streaming capability.

    Built by `open_stream`; constructing it directly bypasses that function's
    checks. It is an async context manager *and* an async iterator, because
    ownership and iteration are the same responsibility here: the object that
    pulls from the producer is the object that must close it.

    Single-owner and single-task. Two consumers pulling one producer is not
    supported and is not made to look supported: re-entry raises. The deadline
    bound and the producer's finalization both assume the task that opened the
    stream is the task that drains and closes it.
    """

    __slots__ = (
        "_context",
        "_events",
        "_execution_id",
        "_generator",
        "_invocation_id",
        "_materializer",
        "_opened",
        "_plan",
        "_stack",
        "_start_ns",
        "_terminal",
        "_tracking_id",
        "_units",
    )

    def __init__(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
        input_materializer: Callable[[TypeSchema, object], object] | None = None,
    ) -> None:
        self._plan = plan
        self._context = context
        self._materializer = input_materializer
        self._stack: contextlib.AsyncExitStack | None = None
        self._generator: AsyncGenerator[Any] | None = None
        self._opened = False
        self._terminal: StreamTerminal | None = None
        self._units = 0
        self._events = bool(plan.hooks)
        self._execution_id = context.execution_id
        self._invocation_id = ""
        self._tracking_id: str | None = None
        self._start_ns = 0

    @property
    def units_emitted(self) -> int:
        """How many units this consumer has received so far."""
        return self._units

    @property
    def terminal(self) -> StreamTerminal | None:
        """How the stream ended, or ``None`` while it is still live."""
        return self._terminal

    @property
    def execution_id(self) -> str:
        """The logical execution identity carried by this stream."""
        return self._execution_id

    async def __aenter__(self) -> Self:
        """Run the whole pre-output phase and stop before the first unit.

        Policies, wire materialization, strict input validation and dependency
        construction all complete here, in the order a complete-result
        invocation uses. The producer is created but not pulled, so a stream
        cannot bypass policy or reach a consumer with unvalidated input
        (RFC 0009 constraint 4).

        Failure here is ordinary: nothing has been exposed, so the exceptions
        are the ones a non-streaming invocation raises and an adapter projects
        them to the canonical `Failure` it already projects (ADR 0084 D6).
        """
        if self._opened:
            raise InvocationError(
                f"the stream for {self._plan.definition.id} is one-shot and has already been "
                "opened; call open_stream() again for a second consumption"
            )
        self._opened = True

        if self._events:
            self._start_ns = time.monotonic_ns()
            self._invocation_id = uuid4().hex
            self._tracking_id = tracking_id(self._context)
            start_event = InvocationStartEvent(
                capability_id=self._plan.definition.id,
                tracking_id=self._tracking_id,
                invocation_id=self._invocation_id,
                execution_id=self._execution_id,
            )
            for hook in self._plan.hooks:
                with contextlib.suppress(Exception):
                    hook.on_invocation_start(start_event)

        stack = contextlib.AsyncExitStack()
        await stack.__aenter__()
        self._stack = stack
        try:
            async with self._bounded():
                await self._start_producer(stack)
        except asyncio.CancelledError:
            self._terminal = StreamTerminal.CANCELLED
            await self._release()
            raise
        except TimeoutError:
            self._terminal = StreamTerminal.TIMED_OUT
            await self._release()
            raise
        except BaseException:
            # The pre-output phase failed before any unit existed, so the
            # ordinary exception travels on unchanged. There is no terminal
            # state: a stream that never started did not end.
            await self._release()
            raise
        return self

    async def _start_producer(self, stack: contextlib.AsyncExitStack) -> None:
        """Evaluate policy and inputs, resolve dependencies, build the producer."""
        plan = self._plan
        context = self._context
        await enforce_policies(plan, context)
        arguments = bind_inputs(plan, context, self._materializer)
        dependencies = await stack.enter_async_context(
            context.di_container.resolve_dependencies(plan.definition.handler, plan.target_deps)
        )
        arguments.update(dependencies)
        arguments.update(dict.fromkeys(plan.context_parameters, context))

        generator = plan.definition.handler(**arguments)
        if not isinstance(generator, AsyncGenerator):
            raise InvocationError(
                f"capability {plan.definition.id} is declared streaming but its handler "
                f"returned {type(generator).__name__}, not an async generator"
            )
        # Pushed after the dependency scope was entered, so the exit stack
        # unwinds the producer first: a producer's `finally` may still use the
        # dependencies it was handed (ADR 0084 D7).
        stack.push_async_callback(generator.aclose)
        self._generator = generator

    def __aiter__(self) -> AsyncIterator[Any]:
        return self

    async def __anext__(self) -> Any:
        """Pull exactly one unit, bounded by the invocation deadline.

        The await reaches the producer directly, which is what makes demand
        real rather than buffered (ADR 0084 D4).

        Raises:
            StopAsyncIteration: the producer was exhausted, or the stream has
                already reached a terminal state.
            StreamInterrupted: the producer failed, or the deadline expired,
                after iteration began.
            asyncio.CancelledError: propagated untouched; cancellation is
                control flow, never a terminal event or a canonical failure.
        """
        generator = self._generator
        if generator is None:
            raise InvocationError(
                f"the stream for {self._plan.definition.id} was iterated before it was opened; "
                "use `async with open_stream(...) as stream`"
            )
        if self._terminal is not None:
            # Python's own async generators report exhaustion after an error,
            # and matching that keeps `async for` usable. `terminal` is the
            # authority on how the stream ended, not this exception.
            raise StopAsyncIteration

        try:
            async with self._bounded():
                unit = await anext(generator)
            unit = validate_output(self._plan, unit)
        except StopAsyncIteration:
            self._terminal = StreamTerminal.COMPLETED
            raise
        except asyncio.CancelledError:
            self._terminal = StreamTerminal.CANCELLED
            raise
        except TimeoutError:
            self._terminal = StreamTerminal.TIMED_OUT
            raise StreamInterrupted(
                Failure(
                    FailureCode.TIMEOUT,
                    "invocation deadline exceeded",
                    execution_id=self._execution_id,
                ),
                self._units,
            ) from None
        except Exception as error:
            self._terminal = StreamTerminal.INTERRUPTED
            raise StreamInterrupted(
                replace(
                    classify(error, self._plan.definition.id),
                    execution_id=self._execution_id,
                ),
                self._units,
            ) from error

        self._units += 1
        return unit

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if exc_type is not None and issubclass(exc_type, asyncio.CancelledError):
            self._terminal = StreamTerminal.CANCELLED
        await self.aclose()
        return False

    async def aclose(self) -> None:
        """Close the producer and release the invocation scope, exactly once.

        Safe to call more than once and safe to call on a stream that was
        never opened. A stream closed before the producer was exhausted ends
        `ABANDONED`, which is a different fact from `COMPLETED` and is
        recorded as one.

        Teardown is deliberately not shielded (ADR 0084 D5). A producer whose
        `finally` awaits during cancellation may be interrupted; shielding it
        here would let one unresponsive producer make cancellation
        unhonourable.
        """
        if self._stack is None:
            return
        if self._terminal is None:
            self._terminal = StreamTerminal.ABANDONED
        await self._release()

    async def _release(self) -> None:
        """Unwind the exit stack once and report the terminal event."""
        stack = self._stack
        if stack is None:
            return
        self._stack = None
        self._generator = None
        try:
            await stack.aclose()
        finally:
            if self._events:
                terminal_event = InvocationTerminalEvent(
                    capability_id=self._plan.definition.id,
                    tracking_id=self._tracking_id,
                    duration_ns=time.monotonic_ns() - self._start_ns,
                    outcome=(self._terminal or StreamTerminal.ABANDONED).value,
                    invocation_id=self._invocation_id,
                    units=self._units,
                    execution_id=self._execution_id,
                )
                for hook in self._plan.hooks:
                    with contextlib.suppress(Exception):
                        hook.on_invocation_terminal(terminal_event)

    def _bounded(self) -> contextlib.AbstractAsyncContextManager[Any]:
        """Bound one await by the invocation's absolute deadline.

        The deadline is an absolute monotonic instant, so bounding every await
        the stream owns against it bounds the whole stream lifetime -- time
        spent waiting on a slow consumer included -- without a timeout object
        that would have to be entered and exited across different awaits
        (ADR 0084 D5).
        """
        deadline = self._context.deadline
        if deadline is None:
            return contextlib.nullcontext()
        return asyncio.timeout_at(deadline)
