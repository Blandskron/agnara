"""Structured telemetry hooks for the execution runtime."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.identity import CapabilityId

__all__ = [
    "InvocationStartEvent",
    "InvocationTerminalEvent",
    "TelemetryHook",
]


@frozen_slots_dataclass
class InvocationStartEvent:
    """Emitted exactly once when an invocation begins."""

    capability_id: CapabilityId
    tracking_id: str | None


@frozen_slots_dataclass
class InvocationTerminalEvent:
    """Emitted exactly once when an invocation terminates."""

    capability_id: CapabilityId
    tracking_id: str | None
    duration_ns: int
    outcome: str


@runtime_checkable
class TelemetryHook(Protocol):
    """Protocol for synchronous execution telemetry observers.

    Callbacks must accept their event and return None synchronously, without
    blocking or raising. Plan construction rejects missing/non-callable
    callbacks and coroutine/generator functions, including callable objects.
    An ordinary hook Exception is silently ignored by the runtime; process
    control and cancellation BaseExceptions are not suppressed.

    The plan freezes the collection, not the hook objects. A shared hook owns
    synchronization of its mutable state and must not replace callbacks after
    compilation. Tracking IDs are caller metadata, not unique span keys.
    Exporter setup, flushing and shutdown belong to the adapter's lifecycle.
    """

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        """Called before a capability's dependencies are resolved."""
        ...

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        """Called after a capability completes, fails, cancels or times out."""
        ...
