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

## 1.0.0 initiatives

### I2 — Streaming model

**Horizon:** `1.0.0`
**Status:** `IN PROGRESS`

One transport-neutral model for cancellation, backpressure and partial failure.
The kernel contract is decided (ADR 0084) and implemented; the transport
projections it unblocks are not started.

### I3 — Execution identity and idempotency

**Horizon:** `1.0.0`
**Status:** `PLANNED`

Reproducible identity and idempotency behavior with release evidence.

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
