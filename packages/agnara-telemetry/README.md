# agnara-telemetry

Explicit OpenTelemetry metrics and span bridges for Agnara's execution hooks.
This
implementation is unreleased repository development beyond `0.1.0a2`.
It imports `agnara` and `opentelemetry-api`, never a sibling adapter or the SDK.

## Composition

The application installs/configures its chosen SDK and supplies a meter:

```python
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from agnara.execution import ExecutionPlan
from agnara_telemetry import OpenTelemetryMetricsHook

# In-memory example: no network exporter or global provider installation.
reader = InMemoryMetricReader()
provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
try:
    hook = OpenTelemetryMetricsHook(provider.get_meter("agnara_telemetry"))
    plan = ExecutionPlan.compile(definition, registry, hooks=[hook])
    # Invoke plans during your application's owned lifecycle.
    # provider.force_flush() may be called by the application when needed.
finally:
    provider.shutdown()
```

`definition` and `registry` are the application's declared capability and DI
registry. Reuse one hook across plans; duplicate hook registration intentionally
duplicates measurements. A supplied `NoOpMeterProvider().get_meter(...)` works
without SDK setup. The package neither selects a global provider nor owns
flush, shutdown, background workers, network endpoints or exporter credentials.

## Measurements

| Instrument | Kind | Unit |
| --- | --- | --- |
| `agnara.invocation.count` | Counter | `1` |
| `agnara.invocation.duration` | Histogram | `s` |

Each terminal callback records one count and the core elapsed duration,
converted from monotonic nanoseconds to seconds. The start callback stores
nothing. Attributes are restricted to `agnara.capability.id` and
`agnara.invocation.outcome`. Outcomes are `success`, `failure`, `timeout` and
`cancellation`; unrecognized direct events map to `unknown`. Negative elapsed
durations are rejected before recording. Use static capability IDs to avoid
unbounded metric cardinality.

No tracking IDs, arguments, return values, exception details or principal
data are added. Applications still control SDK resource attributes, exemplars,
readers and exporters, so review their full export independently. Metric names
are custom Agnara names, not a protocol or GenAI semantic-convention claim.

Counts describe terminal deliveries, not every attempted invocation. Calls
rejected before core emits a start event are excluded. An explicitly returned
canonical `Failure` counts as a successful Python return in the existing core
event semantics. Ordinary instrument errors are isolated by the core runtime;
a failed instrument may leave partial measurements. There are no retries or
exactly-once export promises.

## Ownership and validation

The hook retains only instrument handles; nested/overlapping invocations and
repeated tracking IDs need no correlation map. The supplied meter must support
concurrent, synchronous, non-blocking recording. Do not mutate instruments
while plans are active. A custom blocking instrument blocks invocation.

Development tests use the pinned OpenTelemetry API/SDK 1.44.0 with an in-memory
reader and an in-memory span exporter:
`uv run pytest tests/telemetry tests/architecture`. Tests cover exact
values/units, attributes, span names, status mapping, parent/child nesting,
released correlation state, redaction, runtime outcomes, nested and concurrent
execution, thread sharing, API no-op behavior and application-owned lifecycle.
They do not establish free-threading compatibility, network exporter
conformance, screening of application-added SDK data or performance
superiority.

## Spans

`OpenTelemetryTracingHook(tracer)` opens one span per invocation and ends it on
the matching terminal event:

```python
from opentelemetry.sdk.trace import TracerProvider

from agnara_telemetry import OpenTelemetryTracingHook

provider = TracerProvider(shutdown_on_exit=False)
# The application adds its own span processor and exporter here.
try:
    hook = OpenTelemetryTracingHook(provider.get_tracer("agnara_telemetry"))
    plan = ExecutionPlan.compile(definition, registry, hooks=[hook])
finally:
    provider.shutdown()
```

The span is named after the capability, is `INTERNAL`, and carries only
`agnara.capability.id` and `agnara.invocation.outcome`. `success` sets `OK`;
`failure` and `timeout` set `ERROR` with the outcome word as the description;
`cancellation` is recorded but left `UNSET`, because the caller withdrew rather
than the capability failing. No exception text, argument, result, principal,
transport field or tracking ID is attached, and no span events are recorded.

Pairing uses the runtime's `invocation_id`, never a caller `tracking_id`. That
identity is not exported: it would be unbounded cardinality on every span, and
the span ID already identifies the span.

A nested invocation becomes a child span, because the started span is attached
to the OpenTelemetry context; invocations in sibling tasks are unrelated,
because each task holds its own copy of that context. Register the hook at most
once per plan — a second registration opens a second span for one invocation.
Delivering events to this hook by hand, out of order, is outside the runtime's
nesting guarantee: the spans still end, but the previous context is not
restored.

Metrics and span hooks compose on one plan and can be registered together.

Transport span linking, MCP/GenAI conventions and no-op benchmarks remain
E9.4-E9.6. See [proposed ADR 0054](../../docs/adr/0054-opentelemetry-metrics-bridge.md)
and [proposed ADR 0055](../../docs/adr/0055-capability-invocation-spans.md).
