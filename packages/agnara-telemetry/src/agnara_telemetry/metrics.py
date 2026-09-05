"""Terminal-event metrics using application-owned OpenTelemetry instruments."""

from opentelemetry.metrics import Meter

from agnara.execution import InvocationStartEvent, InvocationTerminalEvent

__all__ = ["OpenTelemetryMetricsHook"]

_OUTCOMES = frozenset({"success", "failure", "timeout", "cancellation"})


class OpenTelemetryMetricsHook:
    """Record terminal deliveries without retaining invocation state.

    Supply a meter at application composition time. The caller owns the SDK,
    exporter configuration and shutdown; this hook never installs a provider.
    Instruments must support synchronous, non-blocking concurrent recording.
    Reuse this hook across plans and register it once on each plan.
    """

    __slots__ = ("_count", "_duration")

    def __init__(self, meter: Meter) -> None:
        if not isinstance(meter, Meter):
            raise TypeError("meter must be an OpenTelemetry Meter")
        self._count = meter.create_counter(
            "agnara.invocation.count", unit="1", description="Terminal invocation hook deliveries"
        )
        self._duration = meter.create_histogram(
            "agnara.invocation.duration", unit="s", description="Core invocation elapsed duration"
        )

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        """No correlation state is needed for terminal-only measurements."""

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        """Record elapsed seconds and the core outcome, without caller metadata."""
        if event.duration_ns < 0:
            raise ValueError("invocation duration must be non-negative")
        attributes = {
            "agnara.capability.id": str(event.capability_id),
            "agnara.invocation.outcome": event.outcome if event.outcome in _OUTCOMES else "unknown",
        }
        self._count.add(1, attributes)
        self._duration.record(event.duration_ns / 1_000_000_000, attributes)
