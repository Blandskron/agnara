# ADR 0086 — Declared Output Contract

- Status: Accepted
- Date: 2026-09-12
- Tracking: GitHub Issue #375
- Initiative: I2
- Amends: ADR 0032's runtime-output premise; ADR 0084 D2 and D6
- Related: ADR 0004, ADR 0022, ADR 0077, ADR 0084, RFC 0009

## Context

ADR 0084 deliberately introduced owned streaming without deciding output
schemas. That avoided giving streams an answer that complete results did not
have, but it left a stable-contract gap: a producer could declare a stream and
emit units whose shape no kernel boundary checked. Existing JSON serializers
can reject non-representable values, but serialization is an adapter concern
and is neither a declared type contract nor a consistent answer for direct
invocation.

The same gap exists for a unary handler. The fix therefore has to be one
capability contract, not a stream-only convention inferred from
`AsyncIterator[T]` or one adapter's `outputSchema` spelling.

## Decision

### D1 — Output is explicit on the capability declaration

`CapabilityDefinition.output` and the `Agnara.capability` and
`App.capability` decorators accept `output=...`. It is an annotation consumed
by the selected schema adapter during `ExecutionPlan.compile`:

```python
@app.capability(output=ReportChunk, streaming=True)
async def generate_report(...) -> AsyncIterator[ReportChunk]:
    yield ReportChunk(...)
```

For a non-streaming capability, `output` describes its successful complete
value. For a streaming capability it describes **each yielded unit**, never a
container containing all units. The default is the explicit unconstrained
contract `typing.Any`; it preserves existing declarations while prohibiting an
adapter from pretending an omitted output has a narrower type.

The kernel does not infer this contract from a return annotation. In
particular, a generator annotation is not a reliable declaration: it cannot
make a handler streaming, identify an ownership boundary or establish what an
adapter is entitled to publish. Return annotations remain ordinary Python
documentation and static-analysis input.

### D2 — Compilation is deterministic and keeps adapters replaceable

The immutable plan exposes one compiled `output_schema`. An explicit output
must compile at startup with the plan's `SchemaAdapter`; an unsupported output
raises `SchemaError` before an invocation exists. `output=Any` is compiled by
the standard kernel adapter so an existing application-specific input adapter
does not have to add a meaningless `Any` case merely because it has no output
contract to refine.

The schema port remains the only schema dependency. No model library, JSON
Schema dialect, transport serializer or vendor result object enters core.

### D3 — Validation happens at the producer boundary

For a complete result, the runtime validates a successful handler value after
the handler completes and before it becomes a `Success`. A handler's explicit
`Failure` is already the canonical outcome and is not a successful output to
validate. The value returned by `TypeSchema.validate` becomes the observed
successful value, just as it does for input validation; the standard adapter
returns the original value.

For a stream, `CapabilityStream` validates one yielded value immediately after
the producer yields it and before incrementing `units_emitted` or returning it
to the consumer. This preserves pull backpressure: validation creates no queue,
prefetch or task. Empty streams validate no unit and finish `COMPLETED` with
zero units.

`ValidationError` from a producer output is never projected as `invalid_input`.
It is converted to an `InvocationError` without the invalid value or nested
path, then classified as the existing redacted `internal_failure`. The handler
violated its own contract; the caller did not supply a bad request.

- A bad first yielded unit raises `StreamInterrupted` with
  `units_emitted == 0` and terminal `INTERRUPTED`. An adapter may use its
  ordinary failure projection because no unit was exposed, but must retain the
  terminal fact for its own lifecycle.
- A bad unit after prior output raises the same exception with the exact count
  already delivered. An adapter must not present that as an atomic failure.
- Cancellation and deadline behavior are unchanged: `CancelledError`
  propagates untouched and deadline expiry remains `timeout` under ADR 0084.

### D4 — Completion carries metadata, not another payload

There is no final data unit and no separate completion payload. `StreamTerminal`
and telemetry remain the sole kernel completion metadata. A Python async
generator cannot return a non-empty value after yielding, and adding a second
final payload would duplicate both the item and terminal contracts. Transport
frames may add transport-specific terminal representation only if their
projection ADR preserves these facts.

### D5 — Adapter obligations are narrow

Adapters consume already validated successful values from the owned execution
boundary. They may use `plan.output_schema.json_schema()` in a later,
separately-governed discovery or wire projection, but cannot invent a different
item type, reclassify output violations as client input, expose invalid-value
diagnostics, or add an in-band core completion event. Serialization can still
fail at a wire boundary; that is a projection concern and does not change the
kernel terminal semantics.

ADR 0032's existing HTTP OpenAPI response remains an unconstrained projection
until a separate HTTP decision deliberately adopts `output_schema`. This record
amends only its former premise that the runtime cannot compile output; it does
not silently add a response-schema or introspection-format promise.

## Threat and concurrency analysis

An output value is application-controlled and can contain secrets or internal
paths. Output validation failures therefore retain no value, schema message or
path in a canonical failure; tests use secret-shaped values to prove this.
Logging continues through the existing redacted classifier. The schema is
compiled into the immutable plan before concurrent invocation, and unit
validation runs in the consumer's pull task. No mutable registry, background
task, buffer or cancellation shield is introduced.

## Consequences

- A capability has one transport-neutral output contract for complete results
  and stream units.
- Existing capabilities remain compatible as `output=Any`; an explicit output
  is additive public syntax while all APIs remain provisional before 1.0.
- The prior unvalidated-unit limitation is closed: `Any` is an intentional,
  visible unconstrained contract, while an explicit output is checked on every
  emitted unit.
- HTTP SSE, WebSockets, MCP progress, A2A and event projections remain outside
  this decision. ADR 0085's SSE implementation work must consume this contract
  and add ASGI conformance evidence; it is not implemented here.

## Alternatives rejected

**Infer the unit type from `AsyncIterator[T]`.** Rejected. It would make a
return annotation silently define a public wire contract while failing to prove
the handler's runtime shape or stream ownership.

**Validate only streams.** Rejected. Unary and streaming results would have
different output semantics, the exact split ADR 0084 identified as unsafe.

**Treat an output violation as `invalid_input`.** Rejected. The caller did not
provide the invalid value, and a schema diagnostic may reveal sensitive handler
data or internal shape.

**Add a terminal data payload.** Rejected. It creates a second completion
vocabulary and duplicates `StreamTerminal` without solving a kernel problem.
