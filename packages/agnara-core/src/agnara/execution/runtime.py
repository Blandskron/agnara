"""Transport-neutral execution of compiled capability plans."""

from __future__ import annotations

import inspect
from typing import Any

from agnara.errors import InvocationError
from agnara.execution.context import ExecutionContext
from agnara.execution.plan import ExecutionPlan

__all__ = ["invoke"]


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

    async with context.di_container.resolve_dependencies(
        plan.definition.handler,
        plan.target_deps,
    ) as dependencies:
        arguments = dict(invocation.payload)
        arguments.update(dependencies)
        arguments.update(dict.fromkeys(plan.context_parameters, context))

        result = plan.definition.handler(**arguments)
        if inspect.isawaitable(result):
            return await result
        return result
