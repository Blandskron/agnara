# ADR 0022 — Canonical Invocation Results

- Status: Proposed
- Date: 2026-09-01
- Tracking: GitHub Issue #71

## Context

Every transport needs the same semantic outcome from a capability invocation,
but HTTP status codes, JSON-RPC errors and other protocol representations do
not belong in `agnara-core`. RFC 0001 proposes ten protocol-neutral failure
categories, and `ARCHITECTURE.md` requires transports to map a canonical
result.

The documented Python API also promises ergonomic direct invocation: callers
receive the handler value and ordinary exceptions propagate. Changing
`invoke(...)` to always return a wrapper would break that API before the first
release and make in-process tests unnecessarily transport-shaped.

## Decision

Core defines:

- `Success[T]`, containing a successful value;
- `Failure`, containing a `FailureCode`, safe message and immutable structured
  details;
- `CanonicalResult[T]`, the union of those outcomes;
- the RFC 0001 categories as the string enum `FailureCode`.

`invoke_result(...)` is the adapter-facing execution boundary. It passes
through an explicit canonical result returned by a handler, wraps an ordinary
handler value in `Success`, and maps runtime exceptions as follows:

| Runtime outcome | Canonical category | Public detail |
| --- | --- | --- |
| `ValidationError` | `INVALID_INPUT` | Validation message and immutable path |
| deadline `TimeoutError` | `TIMEOUT` | Stable deadline message |
| `UnknownCapabilityError` | `NOT_FOUND` | Missing capability message |
| any other `Exception` | `INTERNAL_FAILURE` | Stable redacted message |

External cancellation is runtime control flow, not a capability failure.
`CancelledError` therefore always propagates.

`invoke(...)` remains the direct Python boundary and retains raw
value/exception semantics. Both entry points execute the same compiled plan;
the result boundary adds only outcome classification.

## Considered alternatives

### Change `invoke(...)` to always return `CanonicalResult`

Rejected because it breaks the documented direct-call contract and forces
transport concerns into ordinary Python tests.

### Use exceptions as the only canonical model

Rejected because adapter authors would independently classify exceptions and
could produce inconsistent semantics across protocols.

### Put protocol codes on core exceptions

Rejected because it would make HTTP or another transport the semantic source
of truth.

## Consequences

Positive:

- transports receive one stable, exhaustive failure vocabulary;
- handler exception text is not exposed accidentally;
- direct invocation remains ergonomic and compatible;
- cancellation ownership stays with structured concurrency.

Negative:

- there are two explicit invocation boundaries to document;
- handlers returning canonical types reserve those types as semantic outcomes;
- future domain/policy failures need deliberate mappings into the existing
  taxonomy.

## Guardrails

- result value types use the frozen-slot mechanism from ADR 0020;
- failure details contain only immutable protocol-neutral data;
- core contains no transport status codes or SDK objects;
- adapters map `FailureCode` rather than inspect exception strings;
- tests prove that unexpected exceptions are redacted and cancellation is not
  swallowed.

## Revisit when

- policy evaluation adds typed authorization failures;
- streaming requires partial-success semantics;
- a future major API revision considers making canonical results the only
  invocation boundary.
