# ADR 0025 — Compiled Input Validation Order

- Status: Proposed
- Date: 2026-09-02
- Tracking: GitHub Issue #111

## Context

The schema port already compiles Python annotations into immutable validators,
and RFC 0001 says an execution plan owns validators. The runtime did not yet
connect those contracts: payloads reached handlers as unchecked keyword
arguments, so missing, unexpected, and invalid values became late Python
errors. HTTP binding would otherwise need to become the first place that
enforced capability input semantics.

Validation also needs an explicit place in the security-sensitive invocation
order. Running it before policy evaluation can reveal input-shape information
to a caller who is not authorized to invoke the capability. Running it after
dependency construction allocates resources for input that cannot be used.

## Decision

`ExecutionPlan` compiles a `TypeSchema` for every ordinary typed handler input
at startup. It excludes dependency and `ExecutionContext` parameters, rejects
ambiguous positional-only or variadic inputs, and stores only immutable schema
metadata. The strict standard-library adapter is the default; callers may
supply any structural `SchemaAdapter` during compilation.

At invocation time the runtime preserves this order:

1. verify plan/context composition and reject runtime-owned payload keys;
2. begin the telemetry scope and caller deadline;
3. evaluate pre-handler policies in declaration order;
4. reject unexpected or missing inputs and validate supplied values;
5. construct invocation-scoped dependencies;
6. invoke the handler with validated values.

The value returned by each `TypeSchema.validate` call is passed to the handler,
so a boundary-specific schema adapter may perform documented coercion. The
original invocation payload is never mutated. Validation failures use the
existing protocol-neutral `ValidationError` and canonical `INVALID_INPUT`
mapping.

## Consequences

- HTTP, MCP, A2A, tasks, and direct calls share one semantic validation path.
- Unauthorized callers encounter policy outcomes before schema diagnostics.
- Invalid input never constructs dependencies or invokes application code.
- Unsupported annotations and ambiguous callable shapes fail deterministically
  during startup rather than on first use.
- Direct invocation remains strict by default; wire-format conversion stays in
  the adapter that understands that wire format.
- Per-invocation validation adds measurable work to the hot path, so the E4.9
  benchmark baseline must be rerun and recorded with this change.

## Guardrails

- Core imports no transport or third-party schema implementation.
- Policies remain ahead of validation unless a later security ADR replaces
  this decision with tests for disclosure and authorization behavior.
- Validation precedes dependency construction.
- Compiled schemas must satisfy the immutable, thread-safe `TypeSchema`
  contract.
