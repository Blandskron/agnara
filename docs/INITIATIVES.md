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
| I3 — Execution identity and idempotency | ADR 0087 and the runtime identity exist; no idempotency store, deduplication or result reuse exists. | Operational idempotency store semantics plus race, TTL and failure-retention evidence. | Implement the explicit store boundary and its evidence without coupling it to a transport or automatic retry. |
| I8 — Capability composition | RFC 0005 remains open; no nested invocation contract exists. | A policy-safe composition decision and propagated context/deadline/identity semantics. | Research and RFC work can proceed; runtime awaits the relevant I3 and I10 boundaries. |
| I9 — Public API governance | All current exports are provisional and mechanically classified. | A maintainer-approved stable/deprecated classification with migration evidence. | Audit and prune the public surface in parallel with other initiatives. |
| I10 — Security program | The retained threat model is historical; the 1.0 program is not closed. | Current threat-boundary analysis, supply-chain evidence and abuse/failure tests. | Threat-model and supply-chain design work can proceed in parallel; it constrains I3, I8 and I20 implementation. |
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
tracking and telemetry invocation identifiers and has no persistence, replay or
retry behavior. Operational idempotency still requires its explicit store,
race/TTL/failure evidence and release review.

### I8 — Capability composition

**Horizon:** `1.0.0`
**Status:** `RESEARCH`

A policy-safe nested-invocation contract.

### I9 — Public API governance

**Horizon:** `1.0.0`
**Status:** `IN PROGRESS`

Generated public reference and a deliberate stable classification decision.

### I10 — Security program

**Horizon:** `1.0.0`
**Status:** `PLANNED`

Authentication/delegation design, supply-chain evidence and threat-model closure.

### I14 — Performance program

**Horizon:** `1.0.0`
**Status:** `PLANNED`

Measured budgets and a CI regression gate.

### I20 — Framework interoperability

**Horizon:** `1.0.0`
**Status:** `RESEARCH`

A framework-neutral embedding contract and conformance evidence.

## Deliberately after 1.0.0

Durable execution, workflow orchestration, plugins, multitenancy and new
protocol projections remain research or post-release work. They must not be
smuggled into the stable-release scope without an RFC and a backlog item.

## Prioritization

When work competes, choose architectural prerequisites, security impact,
semantic leverage, public API stability, technical risk, performance and
developer experience—in that order. Feature count and framework popularity are
not priority signals.
