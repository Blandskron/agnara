# ADR 0054 — Application-owned OpenTelemetry Metrics Bridge

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #216 (E9.2)

## Context

ADR 0023 and E9.1 supply synchronous start/terminal hooks. Terminal events
already carry elapsed monotonic nanoseconds, capability identity and outcome.
Tracking IDs are caller input, not unique invocation identities. Pairing
events through a global dictionary would invent correlation semantics and
shared mutable state that metrics do not require.

The OpenTelemetry Python instrumentation guidance recommends API-only
dependencies for libraries; applications configure the SDK. Its metrics API
separates instrument construction from synchronous measurement recording.

## Proposed decision

Add `OpenTelemetryMetricsHook(meter)` in `agnara_telemetry`, implementing the
existing core hook structurally. The caller supplies an OpenTelemetry API
`Meter`; no global provider is read or installed. Construct instruments once:

| Instrument | Kind | Unit | Meaning |
| --- | --- | --- | --- |
| `agnara.invocation.count` | Counter | `1` | Terminal hook deliveries |
| `agnara.invocation.duration` | Histogram | `s` | Core elapsed nanoseconds divided by one billion |

Both use only `agnara.capability.id` and `agnara.invocation.outcome` attributes.
Outcomes are `success`, `failure`, `timeout`, `cancellation`, or `unknown`
for an unrecognized direct event. Negative durations fail before recording.
These are Agnara custom names, not OpenTelemetry protocol/GenAI conventions.
Capability IDs should be static registration identities, never per-user IDs.

The start callback is intentionally empty. Every terminal callback records
independently: repeated tracking IDs, nested invocations and overlapping tasks
need no adapter-owned correlation map. Do not emit tracking IDs, argument or
result data, error text, principal metadata or transport fields. SDK resource
attributes, exemplars and exporter configuration remain application-owned;
this attribute allowlist is not a guarantee about an application's full export.

The hook keeps only the instruments, with no mutable invocation state or
locks. Concurrency of measurement recording belongs to the supplied meter's
implementation. No free-threaded compatibility claim is made. Reuse a hook
across plans, do not mutate its instruments while active, and register it once
per plan unless duplicated measurements are intentional.

The application owns provider/reader/exporter setup, background workers,
flush and shutdown. The adapter does not configure a network destination or
own tasks. Hook callbacks record synchronously and rely on the configured SDK
to meet the core non-blocking observer contract. A blocking custom instrument
is not made asynchronous by this adapter.

The existing runtime suppresses ordinary hook exceptions. Do not add retries:
if one instrument fails, a partial measurement is possible and must not be
presented as an exactly-once delivery guarantee. Process-control exceptions
retain core behavior. Counts measure emitted terminal events, not all attempted
calls; validation rejected before start is excluded. An explicitly returned
canonical `Failure` is still a successful Python return under the current
core event contract. No semantic reinterpretation occurs in this adapter.

## Alternatives and scope

Creating/configuring an SDK provider inside the hook would take ownership of
application resources and exporters; reject it. Correlating start and terminal
events to spans needs a separately reviewed execution-context contract;
defer it to E9.3/E9.4. Emitting start counters adds partial-lifecycle metrics
without a current requirement; keep this first bridge terminal-only.

E9.3 settled that deferred contract: the runtime now supplies an opaque
`invocation_id` on both events, and ADR 0055 builds spans on it. Nothing in
this bridge changes. Metrics still need no correlation, the start callback
stays empty, and the two hooks compose on one plan.

E9.5 reconsidered these attributes and kept them. ADR 0057 adopts `error.type`
on error spans but deliberately not on these instruments: the existing
`agnara.invocation.outcome` already carries that information on every
measurement, so a second attribute present only on failures would fragment
time series without adding signal. Spans and metrics therefore carry different
attribute sets on purpose, which a test records.

This is a bounded initial E9.2 implementation. Traces, span linking,
MCP/GenAI compatibility and no-op cost evidence remain E9.3-E9.6. Proposed
status does not claim maintainer architectural approval.

## Evidence and dependencies

Only `agnara-telemetry` depends on `opentelemetry-api`. The development group
pins `opentelemetry-sdk==1.44.0` for in-memory metric reader tests; it is not
a distributable dependency. No package versions change. Real SDK tests cover
measurement shape, lifecycle outcomes, concurrent/nested runtime invocations,
redaction and explicit provider shutdown. API no-op tests require no SDK setup.

Primary sources checked on 2026-09-05:

- [Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
- [Metrics API](https://opentelemetry.io/docs/specs/otel/metrics/api/)
- [Python metrics API](https://opentelemetry-python.readthedocs.io/en/latest/api/metrics.html)
- [Published API baseline](https://pypi.org/project/opentelemetry-api/1.44.0/)
- [Published SDK baseline](https://pypi.org/project/opentelemetry-sdk/1.44.0/)
