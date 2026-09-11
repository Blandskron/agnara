# Initiatives

This document groups the work required for Agnara's first stable release.
`BACKLOG.md` owns executable work items; `docs/releases/RELEASE_PLAN.md` owns
the gates that must pass before `1.0.0` can be authorized.

<<<<<<< HEAD
This file owns *what should be built and in what order*. `BACKLOG.md` owns the
decomposed items for work that is close enough to implement.
`docs/MATURITY.md` owns what exists. `docs/releases/RELEASE_PLAN.md` owns the
gates a release must pass.

An initiative is not a ticket. It is decomposed into backlog items when it
reaches the front of the queue — earlier decomposition produces tickets that
are wrong by the time anyone reads them.

## Horizons

No calendar dates. A date without evidence is a fabrication, and Agnara has no
evidence about when any of this will be done.

| Horizon | Meaning |
| --- | --- |
| `NOW` | Prepare or decide during the current alpha line. |
| `NEXT ALPHA` | Required before the next alpha can be cut. |
| `LATER ALPHA` | Within the alpha line, order fixed by dependencies. |
| `BETA` | Required before a beta. |
| `1.0` | Required before a stable release. |
| `POST-1.0` | Deliberately after 1.0. |
| `RESEARCH` | Needs an RFC before it can be scheduled at all. |

## Delivered

These initiatives have shipped, so they are no longer carried as open work
above. They keep one row each because the dependency graph below,
`BACKLOG.md`, `docs/releases/RELEASE_PLAN.md` and several ADRs still cite them
by id. For what any of them actually produced, read `docs/MATURITY.md` and the
record that settled it -- not an implementation history.

| Id | Subject | Settled by | Still open |
| --- | --- | --- | --- |
| `I1` | Unified exposure model | ADR 0070, and ADR 0071 for phase 3 | nothing |
| `I3` | Execution identity and idempotency behaviour | ADR 0074 | nothing; `0.1.0a9` still gates the behaviour (ADR 0082) |
| `I7` | HTTP request surface | ADR 0072 | scope beyond what `0.1.0a4` owns, classified in ADR 0072 |
| `I9` | Public API governance | ADR 0067, ADR 0074, ADR 0076 | stability promotion, and a generated reference for the public names |
| `I18` | Documentation and DX program | first increment only | progressive examples, error-message quality, startup diagnostics |

The open remainder of `I9` and `I18` is tracked as backlog items rather than
as initiatives, because it is already decomposed.

## Dependency order

The arrows are hard. An initiative cannot responsibly start before what it
points from.
=======
## Delivery order
>>>>>>> 15cdde3ccb0211665dc88e153872be1acdeee5aa

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
**Status:** `DESIGN READY`

One transport-neutral model for cancellation, backpressure and partial failure.

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

<<<<<<< HEAD
### I16 — Multi-tenancy

**Horizon:** `POST-1.0`
**Status:** `RESEARCH`

No tenant concept exists. The reason it appears here at all is that tenant
propagation touches DI, policy, telemetry, caches, task queues, discovery and
persistence — retrofitting it later is far harder than leaving room now.

**`NOW` action:** none, beyond not making tenancy impossible.

### I17 — Audit

**Horizon:** `BETA`
**Status:** `PLANNED`

Telemetry and audit are different systems with different retention, different
consumers and different failure requirements. Agnara has audit's inputs —
principal, policy decision, effects, confirmation, result classification — and
no system that records them.

**Constraint:** never log secrets or raw sensitive payloads by default.

### I19 — Decision record status reconciliation

**Horizon:** `NOW`
**Status:** `PLANNED`

All 64 ADRs carrying a status say `Proposed`, including ADR 0001 (the Python
baseline CI enforces), ADR 0005 (the freeze the runtime implements) and
ADR 0021 (how every release has been versioned). Four of five RFCs say
`Draft`, including RFC 0001, whose subject is the implemented core.

The field therefore carries no information: a reader cannot tell a live
proposal from a decision that has governed the codebase for three releases.

**Why this is not already done:** moving a record from `Proposed` to
`Accepted` asserts that a decision was taken under the repository's
governance. That is a maintainer act, not an editorial one, so this audit
recorded the problem, added `docs/adr/README.md` and `docs/rfc/README.md`
saying plainly that the field is currently meaningless, and left the pass
itself to be run deliberately.

**Scope:** decide each record's true status; mark superseded ones as
superseded rather than editing them; note in RFC 0001 that its `Context`
example shipped as `ExecutionContext`; give ADR 0023 the status line it is
missing.

### I20 — Framework and ecosystem interoperability

**Horizon:** `NOW` (RFC) → `BETA` (implementation, `0.1.0b1`)
**Status:** `RESEARCH` — RFC 0008 proposed
**Depends on:** I1, I7; partially on I2, I3, I8, I10
**Owned release:** `0.1.0b1` (ADR 0068)

**Problem.** Agnara can be run. It cannot be embedded in an application that
already exists, hosted alongside one, or adopted one operation at a time. No
contract states what an external host must do to invoke a capability, and none
states who owns lifecycle, routing, dependency containers, context, principal,
errors and telemetry when two runtimes share a process.

**Motivation.** A framework that requires the whole stack is adopted only by
new projects. Almost every application that would benefit from capability
semantics already has routes, models, sessions, workers and a telemetry
pipeline, and will not fund a rewrite to get them. Progressive adoption is
therefore a strategic requirement, not a convenience.

**Invariants.** Fifteen, listed in `docs/INTEROPERABILITY.md` section 4. The
two that constrain every other decision: `agnara` stays framework-neutral, and
one integration never dictates another's architecture.

**Architecture.** Four modes — standalone, Agnara as host, Agnara embedded,
side-by-side — all expressible in the existing ports-and-adapters structure. If
a mode needs a new architectural style, that is a finding about the current
boundaries rather than a reason to add one.

**Scope:** the framework embedding contract (what a host needs, in ten steps);
the infrastructure adapter contract, per category rather than universal; the
side-by-side composition rules; the progressive adoption path; the integration
matrix; and a conformance suite that verifies an adapter against one shared
scenario rather than per-framework demos.

**Non-goals:** becoming an ORM, broker, scheduler, worker runtime, template
engine, frontend framework, workflow runtime or admin interface; favouring one
framework; a universal adapter over unlike infrastructure; a plugin discovery
model (I13); shipping any integration in any `0.1.0a*` release.

**Risks.** The first framework shapes the boundary and the second cannot
implement it. An embedding contract designed before RFC 0006 settles names
something that then changes. A host's authenticated user is mapped onto a
`Principal` with more authority than the host established — a confused deputy,
and part of I10. Two lifecycles in one process disagree about shutdown order
and in-flight invocations fail at commit.

**Acceptance criteria.** The `0.1.0b1` interoperability gates in
`docs/releases/RELEASE_PLAN.md`, plus: every shipped integration passes the
anti-coupling test in `docs/INTEROPERABILITY.md` section 5; `agnara` still
imports only the standard library; and the standalone mode is no worse than it
was before any of it existed.

**Requires RFC 0008 to be answered** before implementation. Its questions
become ADRs, split along the line between the parts that need I2, I3 and I8 and
the parts that do not.

## Research questions

Items that need an RFC before they can be scheduled. Listed so they are not
mistaken for plans.

| Question | Why it matters |
| --- | --- |
| Should Agnara own a workflow abstraction? | I11. Default answer is no. |
| Should Agnara consume *remote* capabilities (MCP/A2A client)? | Federation. Needs trust, discovery, namespacing and failure semantics first. |
| Do cost and latency metadata have runtime meaning? | Only worth adding if policy or agents act on them. Decorative metadata is rejected. |
| Is a data classification vocabulary justified? | Would drive redaction and policy. Risk of inventing a framework nobody uses. |
| GraphQL or gRPC projections? | Only where the semantic mapping is coherent. Recorded as research, never a `0.1.0b1` commitment, in `docs/INTEROPERABILITY.md`. |
| Framework-level i18n? | Probably an integration pattern, not a framework concern. |
| Does the schema port need a second shipped adapter? | Pydantic and msgspec are experiments; shipping one is a dependency decision. |
=======
Durable execution, workflow orchestration, plugins, multitenancy and new
protocol projections remain research or post-release work. They must not be
smuggled into the stable-release scope without an RFC and a backlog item.
>>>>>>> 15cdde3ccb0211665dc88e153872be1acdeee5aa

## Prioritization

When work competes, choose architectural prerequisites, security impact,
semantic leverage, public API stability, technical risk, performance and
developer experience—in that order. Feature count and framework popularity are
not priority signals.
