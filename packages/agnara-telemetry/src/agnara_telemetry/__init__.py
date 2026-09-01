"""OpenTelemetry bridge for Agnara capability execution.

Owns the mapping from Agnara's telemetry port onto OpenTelemetry spans,
events and metrics, and correlation across transports.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` sections 3 and 4, and EPIC 9 in ``BACKLOG.md``.
"""
