"""Capability spans over application-owned OpenTelemetry tracers."""

import threading
from contextvars import Token

from opentelemetry.context import Context, attach, detach
from opentelemetry.trace import Span, SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.status import Status, StatusCode

from agnara.execution import InvocationStartEvent, InvocationTerminalEvent

__all__ = ["OpenTelemetryTracingHook"]

_OUTCOMES = frozenset({"success", "failure", "timeout", "cancellation"})

#: Outcomes that describe the capability itself going wrong. A cancellation is
#: the caller withdrawing, so it is recorded but left ``UNSET`` rather than
#: reported as an error the capability caused.
_ERROR_OUTCOMES = frozenset({"failure", "timeout"})


class OpenTelemetryTracingHook:
    """Open one span per invocation and end it on the matching terminal event.

    Supply a tracer at application composition time. The caller owns the SDK,
    processor, exporter, flush and shutdown; this hook never installs or reads
    a global provider. Spans are paired through the runtime's
    ``invocation_id``, never through caller-supplied tracking metadata.

    The started span is attached to the OpenTelemetry context, so a capability
    that invokes another capability produces a child span. Attachment is
    per-context: sibling invocations running in separate tasks do not become
    each other's parents. Both callbacks of one invocation run in the same
    task, which is what makes the paired attach and detach balance.

    Reuse this hook across plans, but register it at most once per plan: a
    second registration would open a second span for one identity, and only
    the first is tracked. Concurrent recording safety belongs to the supplied
    tracer's implementation; no free-threading claim is made here.
    """

    __slots__ = ("_lock", "_spans", "_tracer")

    def __init__(self, tracer: Tracer) -> None:
        if not isinstance(tracer, Tracer):
            raise TypeError("tracer must be an OpenTelemetry Tracer")
        self._tracer = tracer
        # Maps a runtime invocation identity to its open span and the context
        # token that restores the previous span. Bounded by concurrently open
        # invocations: the runtime emits the terminal event from a ``finally``
        # block, and that callback always removes the entry first.
        self._spans: dict[str, tuple[Span, Token[Context]]] = {}
        self._lock = threading.Lock()

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        """Start a span and make it the current one for nested invocations."""
        span = self._tracer.start_span(
            str(event.capability_id),
            kind=SpanKind.INTERNAL,
            attributes={"agnara.capability.id": str(event.capability_id)},
        )
        token = attach(set_span_in_context(span))
        with self._lock:
            tracked = self._spans.setdefault(event.invocation_id, (span, token))
        if tracked[0] is not span:
            # A duplicate registration of this hook on one plan. Undo this
            # span rather than replacing the tracked one, whose token must be
            # detached in the reverse order it was attached.
            detach(token)
            span.end()

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        """End the paired span, or ignore a terminal event with no start."""
        with self._lock:
            tracked = self._spans.pop(event.invocation_id, None)
        if tracked is None:
            # The start callback was suppressed by the runtime, or this hook
            # was registered after the invocation began.
            return
        span, token = tracked
        try:
            outcome = event.outcome if event.outcome in _OUTCOMES else "unknown"
            span.set_attribute("agnara.invocation.outcome", outcome)
            if outcome in _ERROR_OUTCOMES:
                # The outcome name is a fixed vocabulary, not error text.
                span.set_status(Status(StatusCode.ERROR, outcome))
            elif outcome == "success":
                span.set_status(Status(StatusCode.OK))
        finally:
            detach(token)
            span.end()
