"""Transport-neutral execution of compiled capability plans."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agnara.errors import (
    InteractionRequiredError,
    InvocationError,
    PolicyDeniedError,
    UnknownCapabilityError,
    ValidationError,
)
from agnara.execution.context import ExecutionContext
from agnara.execution.plan import ExecutionPlan
from agnara.execution.result import CanonicalResult, Failure, FailureCode, Success
from agnara.execution.telemetry import InvocationStartEvent, InvocationTerminalEvent
from agnara.policy import PolicyFailure, PolicyInteractionRequired, PolicySuccess
from agnara.schema import TypeSchema

__all__ = ["invoke", "invoke_result"]


async def invoke(plan: ExecutionPlan, context: ExecutionContext) -> Any:
    """Execute ``plan`` using the invocation and DI container in ``context``.

    Synchronous handlers run inline. Asynchronous handlers, callable objects,
    and synchronous handlers returning an awaitable are all handled by
    awaiting the returned value when necessary. Dependency resource cleanup
    is owned by ``DIContainer.resolve_dependencies`` and therefore also runs
    when the handler raises, awaiting its result fails, or the owning task is
    cancelled. Cancellation is never caught or translated here.
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
        )
        for hook in observers:
            with contextlib.suppress(Exception):
                hook.on_invocation_start(start_event)

    outcome = "success"
    try:
        if context.deadline is None:
            return await _execute(plan, context, input_materializer)
        async with asyncio.timeout_at(context.deadline):
            return await _execute(plan, context, input_materializer)
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
    """
    try:
        value = await _invoke(plan, context, input_materializer=input_materializer)
    except asyncio.CancelledError:
        raise
    except ValidationError as error:
        return Failure(
            FailureCode.INVALID_INPUT,
            error.message,
            details={"path": error.path},
        )
    except TimeoutError:
        return Failure(FailureCode.TIMEOUT, "invocation deadline exceeded")
    except UnknownCapabilityError as error:
        return Failure(FailureCode.NOT_FOUND, str(error))
    except PolicyDeniedError as error:
        return Failure(FailureCode.FORBIDDEN, str(error))
    except InteractionRequiredError as error:
        request = error.request
        return Failure(
            FailureCode.INTERACTION_REQUIRED,
            request.message,
            details={
                "kind": request.kind.value,
                "title": request.title,
                "capability_id": str(request.capability_id),
                "hints": tuple(sorted(request.hints.items())),
            },
        )
    except Exception:
        return Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")

    if isinstance(value, Success | Failure):
        return value
    return Success(value)


def _tracking_id(context: ExecutionContext) -> str | None:
    """Resolve the operator-facing correlation ID reported to observers.

    Two channels carry this concept. ``ExecutionContext(tracking_id=...)`` is
    an explicit parameter a transport sets deliberately — ``agnara-mcp`` fills
    it from the JSON-RPC request id — while ``Invocation.metadata`` is a
    free-form mapping any caller may populate. The explicit parameter wins.

    Only a string is accepted from either source. Metadata is untyped and may
    hold values that must never be exported, so an unusable one is dropped
    rather than stringified into telemetry. This is a correlation label for
    operators, never a pairing key: pair events by ``invocation_id``.
    """
    explicit = context.tracking_id
    if isinstance(explicit, str):
        return explicit
    supplied = context.invocation.metadata.get("tracking_id")
    return supplied if isinstance(supplied, str) else None


async def _execute(
    plan: ExecutionPlan,
    context: ExecutionContext,
    input_materializer: Callable[[TypeSchema, object], object] | None,
) -> Any:
    """Enforce policies, validate inputs, resolve dependencies, and call the handler."""
    for policy in plan.policies:
        result = await policy.evaluate(context)
        if isinstance(result, PolicySuccess):
            continue
        if isinstance(result, PolicyFailure):
            raise PolicyDeniedError(result.reason)
        if isinstance(result, PolicyInteractionRequired):
            raise InteractionRequiredError(result.request)
        raise TypeError(f"policy returned an invalid result: {type(result).__name__}")

    payload = context.invocation.payload
    if input_materializer is not None:
        payload = _materialize_inputs(plan, payload, input_materializer)
    arguments = _validate_inputs(plan, payload)
    async with context.di_container.resolve_dependencies(
        plan.definition.handler,
        plan.target_deps,
    ) as dependencies:
        arguments.update(dependencies)
        arguments.update(dict.fromkeys(plan.context_parameters, context))

        result = plan.definition.handler(**arguments)
        if inspect.isawaitable(result):
            return await result
        return result


def _validate_inputs(plan: ExecutionPlan, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a payload against precompiled schemas without mutating it.

    A runtime-owned parameter -- one bound to a dependency or to the execution
    context -- is not an input, so a payload naming one is "unexpected input"
    like any other undeclared key. It is deliberately not told apart: the
    check runs after policies, and answering differently would let a caller
    who is not even authorized to invoke the capability enumerate the names of
    its dependency and context parameters.
    """
    unexpected = sorted(set(payload).difference(plan.input_schemas))
    if unexpected:
        raise ValidationError("unexpected input", path=(unexpected[0],))

    missing = sorted(plan.required_inputs.difference(payload))
    if missing:
        raise ValidationError("required input is missing", path=(missing[0],))

    arguments: dict[str, Any] = {}
    for name, schema in plan.input_schemas.items():
        if name not in payload:
            continue
        try:
            arguments[name] = schema.validate(payload[name])
        except ValidationError as error:
            raise error.at(name) from error
    return arguments


def _materialize_inputs(
    plan: ExecutionPlan,
    payload: dict[str, Any],
    materializer: Callable[[TypeSchema, object], object],
) -> dict[str, Any]:
    """Apply one explicit wire conversion after policy and before validation."""
    materialized: dict[str, Any] = {}
    for name, value in payload.items():
        schema = plan.input_schemas.get(name)
        if schema is None:
            materialized[name] = value
            continue
        try:
            materialized[name] = materializer(schema, value)
        except ValidationError as error:
            raise error.at(name) from error
    return materialized
