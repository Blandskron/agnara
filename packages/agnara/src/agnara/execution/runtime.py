"""Transport-neutral execution of compiled capability plans."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from typing import Any

from agnara.errors import InvocationError, UnknownCapabilityError, ValidationError
from agnara.execution.context import ExecutionContext
from agnara.execution.plan import ExecutionPlan
from agnara.execution.result import CanonicalResult, Failure, FailureCode, Success
from agnara.execution.telemetry import InvocationStartEvent, InvocationTerminalEvent

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

    supplied_protected = plan.protected_parameters.intersection(invocation.payload)
    if supplied_protected:
        rendered = ", ".join(sorted(supplied_protected))
        raise InvocationError(f"invocation payload supplies runtime-owned parameter(s): {rendered}")

    start_ns = time.monotonic_ns()
    start_event = InvocationStartEvent(
        capability_id=plan.definition.id,
        tracking_id=invocation.metadata.get("tracking_id"),
    )
    for hook in plan.hooks:
        with contextlib.suppress(Exception):
            hook.on_invocation_start(start_event)

    outcome = "success"
    try:
        if context.deadline is None:
            return await _execute(plan, context)
        async with asyncio.timeout_at(context.deadline):
            return await _execute(plan, context)
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
        terminal_event = InvocationTerminalEvent(
            capability_id=plan.definition.id,
            tracking_id=invocation.metadata.get("tracking_id"),
            duration_ns=time.monotonic_ns() - start_ns,
            outcome=outcome,
        )
        for hook in plan.hooks:
            with contextlib.suppress(Exception):
                hook.on_invocation_terminal(terminal_event)
    if context.deadline is None:
        return await _execute(plan, context)
    async with asyncio.timeout_at(context.deadline):
        return await _execute(plan, context)


async def invoke_result[T](
    plan: ExecutionPlan,
    context: ExecutionContext,
) -> CanonicalResult[T]:
    """Execute a plan and return its protocol-neutral canonical outcome.

    A handler may return ``Success`` or ``Failure`` explicitly. Ordinary
    values become ``Success``. Known runtime errors receive stable semantic
    categories, while unexpected exceptions are redacted. External task
    cancellation is deliberately not converted into a capability failure.

    Use :func:`invoke` for ergonomic in-process calls that should retain
    ordinary Python value/exception semantics.
    """
    try:
        value = await invoke(plan, context)
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
    except Exception:
        return Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")

    if isinstance(value, Success | Failure):
        return value
    return Success(value)


async def _execute(plan: ExecutionPlan, context: ExecutionContext) -> Any:
    """Resolve dependencies and call the handler within the caller's timeout scope."""
    async with context.di_container.resolve_dependencies(
        plan.definition.handler,
        plan.target_deps,
    ) as dependencies:
        arguments = dict(context.invocation.payload)
        arguments.update(dependencies)
        arguments.update(dict.fromkeys(plan.context_parameters, context))

        result = plan.definition.handler(**arguments)
        if inspect.isawaitable(result):
            return await result
        return result
