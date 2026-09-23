"""Invocation-scoped capability composition primitives."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from agnara.capability.identity import CapabilityId

if TYPE_CHECKING:
    from agnara.execution.context import ExecutionContext
    from agnara.execution.result import CanonicalResult
    from agnara.execution.runtime import CapabilityRuntime

__all__ = ["CapabilityInvoker"]


class CapabilityInvoker:
    """Invoke one complete-result capability through the current runtime.

    A compiled plan supplies this only for the invocation that owns it. It is
    neither an application nor a registry: a handler can name a target but
    cannot register one, select another runtime, or reuse an execution scope.
    """

    __slots__ = ("_context", "_runtime")

    def __init__(self, runtime: CapabilityRuntime, context: ExecutionContext) -> None:
        self._runtime = runtime
        self._context = context

    async def invoke(
        self,
        capability_id: CapabilityId,
        payload: Mapping[str, Any],
        *,
        timeout: float | None = None,
    ) -> CanonicalResult[Any]:
        """Invoke a target in the same compiled runtime.

        ``timeout`` is a non-negative relative limit. The child receives the
        earlier of that limit and its parent's absolute deadline; it never
        receives parent confirmation or idempotency state.
        """
        if not isinstance(capability_id, CapabilityId):
            raise TypeError("capability_id must be a CapabilityId")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or timeout < 0
        ):
            raise ValueError("timeout must be a finite non-negative number or None")
        return await self._runtime._invoke_child(
            self._context,
            capability_id,
            dict(payload),
            timeout=None if timeout is None else float(timeout),
        )
