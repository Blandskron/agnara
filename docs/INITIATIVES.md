# Initiatives

This document groups the work required for Agnara's first stable release.
`BACKLOG.md` owns executable work items; `docs/releases/RELEASE_PLAN.md` owns
the gates that must pass before `1.0.0` can be authorized.

## Delivery order

```text
I1 Unified exposure model ──┬─→ I7 HTTP request surface
                            └─→ I20 interoperability
I2 Streaming ───────────────┬─→ transport streaming projections
                            └─→ I5 events
I3 Execution identity ──────┴─→ idempotency and durable-work research
I8 Capability composition ──→ interoperability
I10 Security program ───────→ 1.0.0 authorization
I14 Performance program ────→ 1.0.0 regression gate
I9 Public API governance ───→ 1.0.0 compatibility decision
```

## Foundation dependency register

This is the execution-order map for the active `1.0.0` program. It names
dependencies rather than repeating subsystem status; `docs/MATURITY.md` owns
what exists and `docs/releases/RELEASE_PLAN.md` owns which evidence closes the
release.

| Initiative | Current decision boundary | Cannot close until | Legitimate work now / in parallel |
| --- | --- | --- | --- |
| I2 — Streaming | Kernel implemented by ADR 0084 and ADR 0086; HTTP SSE implemented by ADR 0085 with ASGI conformance evidence. | Nothing further is required for 1.0. | Defer WebSockets, MCP progress, A2A events and event-adapter projections until after 1.0. |
| I3 — Execution identity and idempotency | ADRs 0087–0089 and 0091 define identity, storage and an explicit direct runtime boundary. | Streaming interaction decision and release review. | Keep idempotency transport-neutral and separate from automatic retry; HTTP/MCP selector projections require their own accepted contracts. |
| I8 — Capability composition | ADR 0093's same-compiled-application complete-result boundary is implemented with deterministic policy, confirmation, lifecycle and abuse evidence. | Release review and the separate decisions for delegation, streams and hosts/cross-app composition. | Keep the implemented boundary narrow; delegation, streams and host/cross-app work retain their separate decisions. |
| I9 — Public API governance | The 1.0 inventory contains 166 stable canonical exports across 13 modules, with migration evidence. | Formal maintainer review of the 1.0 compatibility PR. | Keep aliases and implementation modules outside the governed surface. |
| I10 — Security program | The current 1.0 threat-boundary analysis and abuse/failure evidence are recorded; it is not release authorization. | Human release review, final-candidate supply-chain readback/audit and any accepted disposition of residual deployment risk. | Keep host identity, durable stores, exporters and application policy explicitly outside framework claims; threat-model and supply-chain work constrain I3, I8 and I20. |
| I14 — Performance program | Baselines exist, but no budgets or CI regression gate. | Reviewed methodology, calibrated budgets and a failing/pass CI proof. | Establish methodology in parallel; calibrate final thresholds after affected execution semantics settle. |
| I20 — Framework interoperability | RFC 0008 remains open; no embedding contract or conformance harness exists. | The approved host boundary plus standalone, hosted, embedded and side-by-side evidence. | Contract research can proceed; host implementations wait for the I3, I8 and I10 boundaries RFC 0008 identifies. |

## 1.0.0 initiatives

### I2 — Streaming model

**Horizon:** `1.0.0`
**Status:** `IN PROGRESS`

One transport-neutral model for cancellation, backpressure, typed output and
partial failure. The kernel contract is decided (ADR 0084, ADR 0086) and
implemented, and the first transport projection with it: HTTP SSE (ADR 0085).
WebSockets, MCP progress, A2A events and event-adapter projections are not
started.

### I3 — Execution identity and idempotency

**Horizon:** `1.0.0`
**Status:** `IN PROGRESS`

Runtime execution identity is implemented by ADR 0087: it remains distinct from
tracking and telemetry invocation identifiers and has no persistence, automatic
retry or durable-execution behavior. ADR 0091 makes explicitly configured,
direct complete-result idempotency operational over ADR 0089's store;
deterministic race, inclusive-TTL, failure and store-conformance evidence is
complete. Streaming interaction and release review remain required. HTTP and
MCP do not accept idempotency selectors.

The V1-15 audit adds deterministic evidence for atomic claims, exact TTL
boundaries, failure and cancellation cleanup, bounded capacity, stale-state
rejection, sensitive-data redaction and a reusable store conformance suite.
I3 remains in progress because transport selector projections and the
process-local store's deployment limitations remain intentionally open.

### I8 — Capability composition

**Horizon:** `1.0.0`
**Status:** `IN PROGRESS`

ADR 0093's policy-safe `CapabilityRuntime` invokes a complete-result child
only from the same frozen plan snapshot. Deterministic evidence covers
independent policy/confirmation and validation, child context/DI isolation,
deadline/cancellation across two child levels, telemetry-tree linkage,
bounded correlation, direct/indirect recursion-depth refusal and idempotency
isolation. Composition refuses streaming children with a canonical conflict
before producer start, and streaming parents cannot receive an invoker. A child
receives only a detached direct actor; delegated, stream and cross-app
composition remain deferred.

### I9 — Public API governance

**Horizon:** `1.0.0`
**Status:** `IN PROGRESS`

Generated public reference and a deliberate stable classification decision.

### I10 — Security program

**Horizon:** `1.0.0`
**Status:** `IN PROGRESS`

V1-37 closed the supply-chain evidence gaps: a deterministic CycloneDX SBOM
for the built candidate, the recorded artifact digests enforced at every job
that handles the bundle, and the locked dependency audit promoted from a
maintainer instruction to a release gate. Provenance remains PEP 740
attestations; the live publisher configuration cannot be established without
an authorized release and stays `NEEDS CI`.

V1-36 added the property-based and bounded-fuzz lanes in `tests/property/`,
which found and fixed two request-path defects (F-1, F-2) in HTTP method
handling. The lanes are derandomized and bounded so CI stays reproducible;
continuous fuzzing and a crash corpus remain out of 1.0 scope.

V1-35 stabilized the authentication/authorization boundary: the verified
authority inputs are immutable for an execution, a credential object cannot
pose as a principal, and `tests/security/test_authority_boundary.py` holds the
confused-deputy, forged-claim, cached-discovery, verifier-failure and
cross-execution regression evidence. It fixed S-2, an amplification path where
a handler could reassign the actor its nested children inherit. Delegation
remains unimplemented because RFC 0005 is still Draft.

V1-34 replaces the historical A8 model with current candidate evidence for
execution identity, direct/HTTP/MCP/embedded invocation, composition,
idempotency, streaming, schema/persistence and telemetry boundaries. It also
records the point-in-time Dependabot and secret-scanning readback. The I10
program remains open: native HTTP authentication and delegation are not
framework features; durable stores, host identity, telemetry exporters and
application policy remain external boundaries; maintainer release review and
the final-candidate audit are still required.

### I14 — Performance program

**Horizon:** `1.0.0`
**Status:** `PLANNED`

Measured budgets and a CI regression gate.

### I20 — Framework interoperability

**Horizon:** `1.0.0`
**Status:** `DESIGNED`

ADR 0094 accepts the framework-neutral embedding contract. Version-pinned host
fixtures and conformance evidence remain required; no framework integration is
supported by the decision alone.

## Deliberately after 1.0.0

Durable execution, workflow orchestration, plugins, multitenancy and new
protocol projections remain research or post-release work. They must not be
smuggled into the stable-release scope without an RFC and a backlog item.

## Prioritization

When work competes, choose architectural prerequisites, security impact,
semantic leverage, public API stability, technical risk, performance and
developer experience—in that order. Feature count and framework popularity are
not priority signals.
