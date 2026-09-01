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

    Hooks must be synchronous, non-blocking, and never raise exceptions.
    A hook failure will be logged/ignored by the runtime but will not fail
    the capability execution.
    """

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        """Called before a capability's dependencies are resolved."""
        ...

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        """Called after a capability completes, fails, cancels or times out."""
        ...
