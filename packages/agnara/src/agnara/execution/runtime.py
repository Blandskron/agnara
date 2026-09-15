"""Transport-neutral execution of compiled capability plans."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any, NoReturn
from uuid import uuid4

from agnara.capability.identity import CapabilityId
from agnara.capability.metadata import Idempotency
from agnara.errors import InvocationError
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
from agnara.execution.plan import ExecutionPlan
from agnara.execution.result import CanonicalResult, Failure, Success
from agnara.execution.telemetry import InvocationStartEvent, InvocationTerminalEvent
from agnara.schema import TypeSchema

__all__ = ["classify_failure", "invoke", "invoke_result"]


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
    return await _invoke(plan, context, input_materializer=None)


async def _invoke(
    plan: ExecutionPlan,
    context: ExecutionContext,
    *,
    input_materializer: Callable[[TypeSchema, object], object] | None,
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
                    lambda: _execute_with_idempotency(plan, context, input_materializer),
                ),
            )

        # A claim assigns the logical execution identity.  Prepare this
        # boundary before emitting telemetry so start and terminal events pair
        # on the same identity, while the start event still precedes dependency
        # construction and handler work.
        try:
            if context.deadline is None:
                operation = await _prepare_idempotent_execution(plan, context, input_materializer)
            else:
                async with asyncio.timeout_at(context.deadline):
                    operation = await _prepare_idempotent_execution(
                        plan, context, input_materializer
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
    try:
        value = await _invoke(plan, context, input_materializer=input_materializer)
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
) -> Any:
    """Run the ordinary shared preflight without an idempotency option."""
    await enforce_policies(plan, context)
    arguments = bind_inputs(plan, context, input_materializer)
    return await _execute(plan, context, arguments)


async def _prepare_idempotent_execution(
    plan: ExecutionPlan,
    context: ExecutionContext,
    input_materializer: Callable[[TypeSchema, object], object] | None,
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
) -> Any:
    """Execute, abandon failures, and publish one successful claimed result."""
    try:
        value = await _execute(plan, context, arguments)
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
) -> Any:
    """Resolve dependencies, call the handler, and validate its output."""
    async with context.di_container.resolve_dependencies(
        plan.definition.handler,
        plan.target_deps,
    ) as dependencies:
        arguments.update(dependencies)
        arguments.update(dict.fromkeys(plan.context_parameters, context))

        result = plan.definition.handler(**arguments)
        if inspect.isawaitable(result):
            result = await result
        return validate_output(plan, result)
