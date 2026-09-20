"""Transport-neutral execution of compiled capability plans."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Any, NoReturn
from uuid import uuid4

from agnara.capability.identity import CapabilityId
from agnara.capability.metadata import Idempotency
from agnara.capability.registry import FrozenCapabilityRegistry
from agnara.core.di.resolver import DIContainer
from agnara.errors import InvocationError
from agnara.execution._composition import CapabilityInvoker
from agnara.execution._outcome import classify
from agnara.execution._output import validate_output
from agnara.execution._preflight import bind_inputs, enforce_policies
from agnara.execution._preflight import tracking_id as _tracking_id
from agnara.execution.context import ExecutionContext
from agnara.execution.idempotency import (
    IdempotencyClaimed,
    IdempotencyCompleted,
    IdempotencyConflict,
    IdempotencyConflictError,
    IdempotencyInProgress,
    IdempotencyInProgressError,
    IdempotencyReservation,
    IdempotencyResultCodec,
    IdempotencyStorageError,
    IdempotencyStore,
)
from agnara.execution.invocation import Invocation
from agnara.execution.plan import ExecutionPlan
from agnara.execution.result import CanonicalResult, Failure, FailureCode, Success
from agnara.execution.telemetry import InvocationStartEvent, InvocationTerminalEvent
from agnara.schema import TypeSchema

__all__: list[str] = []


def classify_failure(error: Exception, capability_id: CapabilityId) -> Failure:
    """Classify one raised exception into the canonical failure it deserves.

    This is the rule `invoke_result` applies, published for an adapter that
    owns a boundary the kernel does not complete for it. The HTTP SSE
    projection is the first: `open_stream` raises an ordinary exception for a
    pre-output failure (ADR 0084 D6), and the adapter must answer it with the
    same canonical failure any other boundary would have produced (ADR 0085).

    Reusing this is not a convenience. An adapter that re-derived the rule
    would eventually redact one capability on one transport and not on
    another, which is the divergence ADR 0077 exists to prevent. Unexpected
    exceptions are redacted here: the capability identifier is kept for
    correlation, the message and traceback are not.

    ``asyncio.CancelledError`` must never be passed: cancellation is control
    flow, not an outcome, and callers re-raise it untouched.
    """
    if not isinstance(error, Exception):
        raise TypeError(f"error must be an Exception, got {type(error).__name__}")
    if not isinstance(capability_id, CapabilityId):
        raise TypeError(f"capability_id must be a CapabilityId, got {type(capability_id).__name__}")
    return classify(error, capability_id)


async def invoke(plan: ExecutionPlan, context: ExecutionContext) -> Any:
    """Execute ``plan`` using the invocation and DI container in ``context``.

    Synchronous handlers run inline. Asynchronous handlers, callable objects,
    and synchronous handlers returning an awaitable are all handled by
    awaiting the returned value when necessary. Dependency resource cleanup
    is owned by ``DIContainer.resolve_dependencies`` and therefore also runs
    when the handler raises, awaiting its result fails, or the owning task is
    cancelled. Cancellation is never caught or translated here.

    A streaming capability is refused: this boundary has complete-result
    semantics and cannot own a producer's iteration, cleanup or partial
    failure. Use ``open_stream`` instead (ADR 0084).
    """
    return await _invoke(
        plan,
        context,
        input_materializer=None,
        capability_invoker=None,
    )


async def _invoke(
    plan: ExecutionPlan,
    context: ExecutionContext,
    *,
    input_materializer: Callable[[TypeSchema, object], object] | None,
    capability_invoker: CapabilityInvoker | None,
) -> Any:
    if not isinstance(plan, ExecutionPlan):
        raise TypeError(f"plan must be an ExecutionPlan, got {type(plan).__name__}")
    if not isinstance(context, ExecutionContext):
        raise TypeError(f"context must be an ExecutionContext, got {type(context).__name__}")

    invocation = context.invocation
    if invocation.capability_id != plan.definition.id:
        raise InvocationError(
            f"invocation targets {invocation.capability_id}, but the compiled plan is for "
            f"{plan.definition.id}"
        )
    if plan.streaming:
        # Returning the producer inside `Success` is the alternative RFC 0009
        # section 7 rejects: nobody would own iteration or cleanup, and a
        # failure after output could not be described honestly.
        raise InvocationError(
            f"capability {plan.definition.id} is declared streaming; use open_stream()"
        )

    async def run() -> Any:
        if context.idempotency is None:
            return await _observe_invocation(
                plan,
                context,
                lambda: _within_deadline(
                    context,
                    lambda: _execute_with_idempotency(
                        plan,
                        context,
                        input_materializer,
                        capability_invoker,
                    ),
                ),
            )

        # A claim assigns the logical execution identity.  Prepare this
        # boundary before emitting telemetry so start and terminal events pair
        # on the same identity, while the start event still precedes dependency
        # construction and handler work.
        try:
            if context.deadline is None:
                operation = await _prepare_idempotent_execution(
                    plan,
                    context,
                    input_materializer,
                    capability_invoker,
                )
            else:
                async with asyncio.timeout_at(context.deadline):
                    operation = await _prepare_idempotent_execution(
                        plan,
                        context,
                        input_materializer,
                        capability_invoker,
                    )
        except Exception as error:
            # A rejected preflight or unavailable claim has no claimed logical
            # identity, but it is still an invocation lifecycle with the
            # context's provisional runtime-generated identity.
            operation = _raise_idempotency_error(error)
        return await _observe_invocation(
            plan,
            context,
            lambda: _within_deadline(context, operation),
        )

    return await run()


async def _within_deadline(context: ExecutionContext, operation: Callable[[], Any]) -> Any:
    """Run one observed operation inside its existing absolute deadline."""
    if context.deadline is None:
        return await operation()
    # The established direct boundary deliberately enters the dependency scope
    # before an already-expired timeout is delivered, so acquired resources
    # still exercise their teardown path. A nested child has a stronger
    # confused-deputy boundary: a parent cannot use an exhausted child limit to
    # start even synchronous child work.
    if (
        context._parent_execution_id is not None
        and context.deadline <= asyncio.get_running_loop().time()
    ):
        raise TimeoutError("invocation deadline exceeded")
    async with asyncio.timeout_at(context.deadline):
        return await operation()


async def _observe_invocation(
    plan: ExecutionPlan,
    context: ExecutionContext,
    operation: Callable[[], Any],
) -> Any:
    """Emit the lifecycle pair around work whose logical identity is settled."""
    # Building a lifecycle event pair costs roughly two microseconds, and an
    # application that registered no hook can observe none of it. The work is
    # therefore guarded rather than unconditional; measured by
    # benchmarks/telemetry_overhead.py and recorded by ADR 0058.
    observers = plan.hooks
    start_ns = time.monotonic_ns() if observers else 0
    # Observers need a key that pairs this start with its terminal event.
    # A caller-supplied tracking ID cannot serve: it is optional, repeatable
    # across invocations and attacker-controlled on a remote transport.
    invocation_id = uuid4().hex if observers else ""
    tracking_id = _tracking_id(context) if observers else None
    if observers:
        start_event = InvocationStartEvent(
            capability_id=plan.definition.id,
            tracking_id=tracking_id,
            invocation_id=invocation_id,
            execution_id=context.execution_id,
            parent_execution_id=context._parent_execution_id,
        )
        for hook in observers:
            with contextlib.suppress(Exception):
                hook.on_invocation_start(start_event)

    outcome = "success"
    try:
        return await operation()
    except asyncio.CancelledError:
        outcome = "cancellation"
        raise
    except TimeoutError:
        outcome = "timeout"
        raise
    except Exception:
        outcome = "failure"
        raise
    finally:
        if observers:
            terminal_event = InvocationTerminalEvent(
                capability_id=plan.definition.id,
                tracking_id=tracking_id,
                duration_ns=time.monotonic_ns() - start_ns,
                outcome=outcome,
                invocation_id=invocation_id,
                execution_id=context.execution_id,
                parent_execution_id=context._parent_execution_id,
            )
            for hook in observers:
                with contextlib.suppress(Exception):
                    hook.on_invocation_terminal(terminal_event)


async def invoke_result[T](
    plan: ExecutionPlan,
    context: ExecutionContext,
    *,
    input_materializer: Callable[[TypeSchema, object], object] | None = None,
) -> CanonicalResult[T]:
    """Execute a plan and return its protocol-neutral canonical outcome.

    A handler may return ``Success`` or ``Failure`` explicitly. Ordinary
    values become ``Success``. Known runtime errors receive stable semantic
    categories, while unexpected exceptions are redacted. External task
    cancellation is deliberately not converted into a capability failure.

    Use :func:`invoke` for ergonomic in-process calls that should retain
    ordinary Python value/exception semantics. A JSON transport may pass the
    explicit ``materialize_json`` schema helper as ``input_materializer``;
    conversion then runs after policy and before strict schema validation.

    A streaming capability is refused here for the reason :func:`invoke`
    refuses it: ``Success`` cannot describe a producer, and ``Failure``
    cannot describe an error that arrives after output (ADR 0084).
    """
    return await _invoke_result(
        plan,
        context,
        input_materializer=input_materializer,
        capability_invoker=None,
    )


async def _invoke_result[T](
    plan: ExecutionPlan,
    context: ExecutionContext,
    *,
    input_materializer: Callable[[TypeSchema, object], object] | None,
    capability_invoker: CapabilityInvoker | None,
) -> CanonicalResult[T]:
    try:
        value = await _invoke(
            plan,
            context,
            input_materializer=input_materializer,
            capability_invoker=capability_invoker,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        return replace(classify(error, plan.definition.id), execution_id=context.execution_id)

    if isinstance(value, Success | Failure):
        return replace(value, execution_id=context.execution_id)
    return Success(value, execution_id=context.execution_id)


async def _execute_with_idempotency(
    plan: ExecutionPlan,
    context: ExecutionContext,
    input_materializer: Callable[[TypeSchema, object], object] | None,
    capability_invoker: CapabilityInvoker | None,
) -> Any:
    """Run the ordinary shared preflight without an idempotency option."""
    await enforce_policies(plan, context)
    arguments = bind_inputs(plan, context, input_materializer)
    return await _execute(plan, context, arguments, capability_invoker)


async def _prepare_idempotent_execution(
    plan: ExecutionPlan,
    context: ExecutionContext,
    input_materializer: Callable[[TypeSchema, object], object] | None,
    capability_invoker: CapabilityInvoker | None,
) -> Callable[[], Any]:
    """Preflight and claim before telemetry observes the logical identity.

    Policy and input checks intentionally remain before the claim.  The
    returned operation starts after a claimed or completed identity has been
    adopted and before dependency resolution, so one telemetry lifecycle pair
    cannot contain two execution identities.
    """
    await enforce_policies(plan, context)
    arguments = bind_inputs(plan, context, input_materializer)
    configured = context.idempotency
    assert configured is not None

    if plan.streaming:
        # Defence in depth only. This helper is reached from `invoke`/
        # `invoke_result`, which refuse a streaming plan several frames earlier,
        # so this branch cannot fire today. It was once the *only* statement of
        # this rule, which is exactly how the gap hid: `open_stream` consulted
        # `context.idempotency` nowhere, so a streaming caller's selector was
        # accepted and dropped in silence. The reachable refusal now lives in
        # `open_stream`, next to the other entry guards.
        raise InvocationError("idempotency result reuse is unavailable for streaming capabilities")
    if plan.definition.idempotency is not Idempotency.YES:
        raise InvocationError(
            f"capability {plan.definition.id} is not declared idempotent and cannot use "
            "IdempotencyInvocation"
        )
    if configured.scope.capability_id != plan.definition.id:
        raise InvocationError("idempotency scope capability does not match the compiled plan")
    if configured.scope.principal_id != context.principal.identity:
        raise InvocationError("idempotency scope principal does not match the execution context")

    claim = await configured.store.claim(configured.scope, lease_ttl=configured.lease_ttl)
    if isinstance(claim, IdempotencyConflict):
        return _raise_idempotency_error(IdempotencyConflictError())
    if isinstance(claim, IdempotencyInProgress):
        return _raise_idempotency_error(IdempotencyInProgressError())
    if isinstance(claim, IdempotencyCompleted):
        context._adopt_idempotency_execution_id(claim.execution_id)
        return lambda: _reuse_completed_async(context, configured.codec, claim)
    if not isinstance(claim, IdempotencyClaimed):
        raise IdempotencyStorageError("idempotency store returned an invalid claim result")

    context._adopt_idempotency_execution_id(claim.reservation.execution_id)
    return lambda: _execute_claimed_idempotency(
        plan,
        context,
        arguments,
        configured.codec,
        configured.store,
        claim.reservation,
        configured.result_ttl,
        capability_invoker,
    )


def _raise_idempotency_error(error: Exception) -> Callable[[], Any]:
    async def raise_error() -> NoReturn:
        raise error

    return raise_error


async def _execute_claimed_idempotency(
    plan: ExecutionPlan,
    context: ExecutionContext,
    arguments: dict[str, Any],
    codec: IdempotencyResultCodec,
    store: IdempotencyStore,
    reservation: IdempotencyReservation,
    result_ttl: float,
    capability_invoker: CapabilityInvoker | None,
) -> Any:
    """Execute, abandon failures, and publish one successful claimed result."""
    try:
        value = await _execute(plan, context, arguments, capability_invoker)
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await store.abandon(reservation)
        raise
    except Exception:
        try:
            abandoned = await store.abandon(reservation)
        except Exception as error:
            raise IdempotencyStorageError(
                "idempotency reservation could not be abandoned"
            ) from error
        if not abandoned:
            raise IdempotencyStorageError(
                "idempotency reservation could not be abandoned"
            ) from None
        raise

    if isinstance(value, Failure):
        try:
            abandoned = await store.abandon(reservation)
        except Exception as error:
            raise IdempotencyStorageError(
                "idempotency reservation could not be abandoned"
            ) from error
        if not abandoned:
            raise IdempotencyStorageError("idempotency reservation could not be abandoned")
        return value

    try:
        encoded = codec.encode(value)
        if not isinstance(encoded, bytes):
            raise TypeError("idempotency codec encode() must return bytes")
        completed = await store.complete(
            reservation,
            encoded,
            result_ttl=result_ttl,
        )
    except Exception as error:
        raise IdempotencyStorageError("idempotency result could not be stored") from error
    if not completed:
        raise IdempotencyStorageError("idempotency result could not be stored")
    return value


def _reuse_completed(
    context: ExecutionContext,
    codec: IdempotencyResultCodec,
    completed: IdempotencyCompleted,
) -> object:
    """Decode one stored success without exposing its bytes to normal diagnostics."""
    context._adopt_idempotency_execution_id(completed.execution_id)
    try:
        value = codec.decode(completed.result)
    except Exception as error:
        raise IdempotencyStorageError("idempotency result could not be decoded") from error
    return value


async def _reuse_completed_async(
    context: ExecutionContext,
    codec: IdempotencyResultCodec,
    completed: IdempotencyCompleted,
) -> object:
    """Adapt a completed value to the asynchronous invocation operation."""
    return _reuse_completed(context, codec, completed)


async def _execute(
    plan: ExecutionPlan,
    context: ExecutionContext,
    arguments: dict[str, Any],
    capability_invoker: CapabilityInvoker | None,
) -> Any:
    """Resolve dependencies, call the handler, and validate its output."""
    if plan.capability_invoker_parameters and capability_invoker is None:
        raise InvocationError(
            f"capability {plan.definition.id} requires a CapabilityRuntime invocation boundary"
        )
    async with context.di_container.resolve_dependencies(
        plan.definition.handler,
        plan.target_deps,
    ) as dependencies:
        arguments.update(dependencies)
        arguments.update(dict.fromkeys(plan.context_parameters, context))
        arguments.update(dict.fromkeys(plan.capability_invoker_parameters, capability_invoker))

        result = plan.definition.handler(**arguments)
        if inspect.isawaitable(result):
            result = await result
        return validate_output(plan, result)


class CapabilityRuntime:
    """Immutable same-application runtime for nested capability execution.

    A frozen capability snapshot owns every supplied plan by identity at
    construction. Its only composition surface is the invocation-scoped
    :class:`CapabilityInvoker` injected into handlers that explicitly request
    it. A target absent from this snapshot is not reachable through
    composition.
    """

    __slots__ = ("_container", "_max_composition_depth", "_plans")

    def __init__(
        self,
        capabilities: FrozenCapabilityRegistry,
        plans: Sequence[ExecutionPlan],
        container: DIContainer,
        *,
        max_composition_depth: int = 8,
    ) -> None:
        if not isinstance(capabilities, FrozenCapabilityRegistry):
            raise TypeError("capabilities must be a FrozenCapabilityRegistry")
        if not isinstance(container, DIContainer):
            raise TypeError("container must be a DIContainer")
        if (
            isinstance(max_composition_depth, bool)
            or not isinstance(max_composition_depth, int)
            or not 1 <= max_composition_depth <= 32
        ):
            raise ValueError("max_composition_depth must be an integer from 1 through 32")
        compiled: dict[CapabilityId, ExecutionPlan] = {}
        for plan in plans:
            if not isinstance(plan, ExecutionPlan):
                raise TypeError("plans must contain ExecutionPlan instances")
            capability_id = plan.definition.id
            if (
                capability_id not in capabilities
                or capabilities[capability_id] is not plan.definition
            ):
                raise InvocationError(
                    f"compiled plan for {capability_id} does not belong to this capability snapshot"
                )
            if capability_id in compiled:
                raise InvocationError(f"duplicate compiled plan for capability {capability_id}")
            compiled[capability_id] = plan
        if not compiled:
            raise InvocationError("CapabilityRuntime requires at least one compiled plan")
        self._plans = MappingProxyType(compiled)
        self._container = container
        self._max_composition_depth = max_composition_depth

    async def invoke(self, context: ExecutionContext) -> Any:
        """Invoke the plan named by ``context`` with ordinary Python semantics."""
        plan = self._plan_for(context)
        return await _invoke(
            plan,
            context,
            input_materializer=None,
            capability_invoker=CapabilityInvoker(self, context),
        )

    async def invoke_result[T](
        self,
        context: ExecutionContext,
        *,
        input_materializer: Callable[[TypeSchema, object], object] | None = None,
    ) -> CanonicalResult[T]:
        """Invoke the plan named by ``context`` and return its canonical result."""
        plan = self._plan_for(context)
        return await _invoke_result(
            plan,
            context,
            input_materializer=input_materializer,
            capability_invoker=CapabilityInvoker(self, context),
        )

    async def aclose(self) -> None:
        """Close application-owned singleton dependencies."""
        await self._container.aclose()

    def _plan_for(self, context: ExecutionContext) -> ExecutionPlan:
        if not isinstance(context, ExecutionContext):
            raise TypeError("context must be an ExecutionContext")
        if context.di_container is not self._container:
            raise InvocationError("execution context does not belong to this CapabilityRuntime")
        plan = self._plans.get(context.invocation.capability_id)
        if plan is None:
            raise InvocationError(
                f"no compiled capability is registered for {context.invocation.capability_id}"
            )
        return plan

    async def _invoke_child(
        self,
        parent: ExecutionContext,
        capability_id: CapabilityId,
        payload: dict[str, Any],
        *,
        timeout: float | None,
    ) -> CanonicalResult[Any]:
        """Run one child plan after all composition-boundary refusals."""
        plan = self._plans.get(capability_id)
        if plan is None:
            return Failure(FailureCode.NOT_FOUND, "nested target capability is not available")

        ancestry = (*parent._composition_ancestry, parent.invocation.capability_id)
        if capability_id in ancestry:
            return Failure(FailureCode.CONFLICT, "nested capability recursion is not allowed")
        if len(parent._composition_ancestry) >= self._max_composition_depth:
            return Failure(FailureCode.CONFLICT, "nested capability depth limit exceeded")
        if plan.streaming:
            # ADR 0093 deliberately has complete-result semantics.  Returning
            # a stream here would leave iteration, backpressure, partial
            # failure and cleanup without one owner.
            return Failure(
                FailureCode.CONFLICT,
                "nested streaming capability cannot be invoked",
            )

        deadline = parent.deadline
        if timeout is not None:
            child_deadline = asyncio.get_running_loop().time() + timeout
            deadline = child_deadline if deadline is None else min(deadline, child_deadline)

        child = ExecutionContext._child(
            parent,
            Invocation(capability_id, payload, {}, deadline),
        )
        return await _invoke_result(
            plan,
            child,
            input_materializer=None,
            capability_invoker=CapabilityInvoker(self, child),
        )
