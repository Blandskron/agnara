# Initiatives

Future work, clustered into coherent architectural initiatives and ordered by
dependency rather than by appetite.

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

## Dependency order

The arrows are hard. An initiative cannot responsibly start before what it
points from.

```text
I1 Exposure model ──┬─→ I4 A2A
                    ├─→ I5 Events
                    └─→ I7 HTTP request surface

I2 Streaming ───────┬─→ HTTP SSE / WebSockets
                    ├─→ MCP progress
                    ├─→ A2A streaming
                    └─→ I5 Events

I3 Execution identity ──→ I6 Durable execution ──→ I11 Workflows
                     └──→ resilience, retries

I8 Composition ─────────→ I11 Workflows

I9 Public API governance ──→ 1.0

I10 Security program ───────→ BETA

I1 ──┬─→ I20 Interoperability ──→ 0.1.0b1
I7 ──┤
I3 ──┤        (I2, I8, I10 gate the parts that touch
I2 ──┤         streaming, nesting and the principal
I8 ──┤         bridge — see RFC 0008 section 6)
I10 ─┘
```

`I1` and `I2` are the two initiatives most other work waits on. Neither is
large. Both are design-first.

## The initiatives

### I1 — Unified exposure model

**Horizon:** `NEXT ALPHA`
**Status:** `IMPLEMENTED` — RFC 0006 answered by ADR 0070
**Blocks:** I4, I5, I7, a stable public composition API, 1.0

**Decided and built.** `agnara.exposure` owns neutral identity, per-surface
adapter compilation and one frozen availability registry. Declaration belongs
to the composition root; each adapter derives its records from its own
compiled dispatch artifact; introspection reads the registry instead of being
told about exposures a second time. Both shipped adapters go through it, and a
third would need no kernel change. ADR 0070 records the five spike decisions
and the rejected alternatives.

**What this did not deliver.** `agnara-http` still exports nothing. The model
beneath the composition API is settled; the API itself is the next piece of
work, and until it exists an application cannot compose HTTP through
supported entry points. `docs/API_DESIGN.md` section 4 remains a sketch, and
`docs/releases/STATUS.md` still carries that blocker.

**Non-goals, honoured:** no third adapter was built to prove the model, and
no ecosystem integration was added.

### I2 — Streaming model

**Horizon:** `NOW` (RFC) → `LATER ALPHA`
**Status:** `RESEARCH`
**Blocks:** HTTP SSE and WebSockets, MCP progress, A2A streaming, events, task
progress

Nothing in the kernel returns a stream. If each adapter adds streaming
separately, cancellation, backpressure and partial-failure semantics will
differ per transport and the "one capability, many surfaces" promise will stop
applying to streaming capabilities.

**Must decide:** what a streaming capability returns; ownership and cleanup of
the stream; cancellation and disconnect; backpressure; what a failure *after*
partial output means, in a model where failures are canonical values;
completion semantics; how telemetry spans a stream rather than a call.

**Requires an RFC** before any adapter work.

### I3 — Execution identity and idempotency behaviour

**Horizon:** `LATER ALPHA`
**Status:** `PLANNED`
**Blocks:** I6, resilience, event delivery semantics

Idempotency is declared and published; the runtime does nothing with it. Safe
retry, deduplication and replay all need an identity that outlives one
invocation.

**Scope:** execution identity, idempotency keys, deduplication window,
result reuse, pluggable storage contract, and the transport mappings that
follow.

**Explicit constraint:** never retry a non-idempotent capability
automatically. The declared metadata exists precisely so the runtime does not
have to guess.

### I4 — A2A adapter

**Horizon:** `BETA`
**Status:** `PLANNED`
**Depends on:** I1, I2, I6 (for task-shaped skills)

Agent Card and skill projection over the same primitives as everything else.

**Constraint:** if A2A appears to need its own execution engine, the
capability runtime is wrong and that is the finding, not a reason to build a
second engine.

### I5 — Events and AsyncAPI

**Horizon:** `BETA`
**Status:** `PLANNED`
**Depends on:** I1, I2, I3

An event capability model with broker-neutral contracts. AsyncAPI is a
projection, exactly as OpenAPI is for HTTP.

**Scope:** producers, consumers, acknowledgement, retry, dead-letter,
ordering, deduplication, delivery semantics, outbox integration, backpressure,
correlation. Broker clients stay outside.

**Non-goal:** becoming a broker.

### I6 — Durable execution (tasks)

**Horizon:** `POST-1.0` for the full program, `BETA` for the abstraction
**Status:** `RESEARCH`
**Depends on:** I2, I3

The single largest missing subsystem. Deferred, scheduled, long-running,
retryable, human-gated and distributed execution have no home.

**Approach:** define Agnara's abstraction first and let external engines
implement it. Do not build a Celery or Temporal clone; both are better at
being themselves than a framework subsystem would be.

**Decomposes into:** task identity, state model, persistence contract, retry
and backoff semantics, cancellation, progress and checkpoints, scheduling,
concurrency and priority, worker ownership, recovery after process death,
human approval, compensation, observability.

**Requires an RFC per boundary**, not one RFC for all of it.

### I7 — HTTP request surface

**Horizon:** `NEXT ALPHA`
**Status:** `IMPLEMENTED` for what `0.1.0a4` owns — ADR 0072
**Depends on:** I1

**Done.** Cookies, form fields and file uploads are binding sources, exactly
as predicted: new sources, not new architecture. A login form, a session
cookie and an upload are expressible through public API, their OpenAPI is
truthful, and every failure is a structured RFC 9457 problem.

**Deferred, each with a recorded reason** (ADR 0072): multiple files and
repeated form fields, which need the collection binding ADR 0026 deferred; the
client filename and per-part content type, which need a core-visible upload
value type; streaming request bodies, which need I2; and CORS, compression,
static files, proxy headers and trusted hosts, which belong at the ASGI layer
or the reverse proxy.

**Still deliberately absent:** an extension point for cross-cutting concerns.
"Middleware" in most frameworks is where transport types leak into application
code, and Agnara must not reproduce that. An `HttpApplication` is an ASGI 3
callable, so ordinary ASGI middleware already wraps it from outside, which is
where transport concerns belong.

### I8 — Capability composition

**Horizon:** `BETA`
**Status:** `RESEARCH`
**Blocks:** I11

A capability cannot invoke another with propagated principal, deadline,
cancellation, transaction and telemetry context. Applications will work around
this with direct function calls, which bypasses policy silently — a security
gap disguised as an ergonomics gap.

**Must decide:** nested `ExecutionContext`; what propagates and what does not;
whether policy re-evaluates on an internal call; recursion detection; effect
aggregation; telemetry parent/child.

**Not the same as I20.** I8 is capability-to-capability composition inside
Agnara. I20 is composition with the rest of the ecosystem. They meet at one
question — a capability re-entered through an external host — and RFC 0008 Q12
requires the same answer for both, because two answers would make the host path
a policy bypass.

### I9 — Public API governance

**Horizon:** `NOW`
**Status:** `PLANNED`
**Blocks:** 1.0

Every public name was once an implicit commitment. ADR 0067 and its follow-up
closed the first part of this: 123 exports across seven core modules are
classified `provisional`, and the release gate compares the manifest with each
module's literal `__all__`.

**Remaining scope:** decide the boundary for the 23 further core modules that
declare a public `__all__` and are governed by nothing (Issue #289); add the
completeness test once that decision makes it passable; write the deprecation
policy before the surface is large enough to make one painful; and decide
which names, if any, are promoted to `stable`, which the beta and
release-candidate gates own.

Cheap, and it gets more expensive every release it is deferred.

### I10 — Security program

**Horizon:** `BETA`
**Status:** `PLANNED`

`SECURITY.md` already records that the threat model, dependency audit, secret
scanning, static analysis and private vulnerability reporting are absent, and
the release readiness gate reports it every run.

**Scope:** threat model; security invariants with architecture tests;
authentication integration contracts mapping onto one `Principal`; delegation
and impersonation controls; tenant isolation; confused-deputy analysis at
every protocol boundary; introspection and error leakage review; supply chain
— SBOM, signing, provenance, vulnerability scanning.

**Invariant candidates worth testing:** secrets never reach introspection,
telemetry or errors; a capability's declared effects cannot be widened by an
adapter; policy cannot be bypassed by an internal call.

### I11 — Workflow orchestration

**Horizon:** `RESEARCH`
**Status:** `RESEARCH`
**Depends on:** I6, I8

Whether Agnara should own a workflow abstraction above capabilities is **not
decided**. The honest default is that it should not, and should integrate with
engines that already do this well.

**The RFC must answer** why the kernel is the right home before any design
work starts.

### I12 — Application testing utilities

**Horizon:** `BETA`
**Status:** `PLANNED`

A harness, an invocation client, transport test clients, dependency
overrides, fake principals, policy and telemetry assertions, lifecycle
testing.

**Constraint:** testing utilities must exercise the runtime, not bypass it. A
harness that skips policy evaluation would make tests pass for applications
that fail in production.

### I13 — Plugin and extension model

**Horizon:** `POST-1.0`
**Status:** `RESEARCH`

Discovery, loading, lifecycle, version compatibility, permissions, trust and
failure behaviour — differentiated by plugin kind.

**Timing argument:** defining this before an ecosystem exists is a design
problem; defining it after is a compatibility problem. It is scheduled after
1.0 because the extension points it would expose are not stable yet, not
because it is unimportant.

### I14 — Performance program

**Horizon:** `LATER ALPHA` (budgets) → `1.0` (regression gate)
**Status:** `PLANNED`

Four benchmark baselines exist. There are no budgets and no regression gate,
so a performance regression is currently invisible.

**Scope:** budgets for registration, compilation, invocation, DI, policy
evaluation, serialization, routing and startup; cold and warm path; sync and
async; concurrency; high capability counts; deep DI graphs; a regression gate
in CI.

**Discipline:** benchmark engineering questions, never rankings. A
microbenchmark never becomes a production claim. Native acceleration stays
`DEFERRED` until a measured bottleneck justifies it, and would never redefine
semantics.

### I15 — Free-threaded Python

**Horizon:** `1.0`
**Status:** `RESEARCH`

Immutability after freeze is designed for it and nothing is verified under a
free-threaded build.

**Scope:** audit registries, caches, lifecycle state, serializers, routing,
telemetry and containers for shared mutable state; document thread-safety
contracts explicitly; run the suite under a free-threaded interpreter.

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

### I18 — Documentation and DX program

**Horizon:** `NOW`, continuous
**Status:** `IMPLEMENTED` (this initiative's first increment)

The canonical document set and its ownership map, plus automated consistency
checks. Then: progressive examples, reference applications, error message
quality, and startup diagnostics.

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
model (I13); shipping any integration in `0.1.0a4` or `0.1.0a5`.

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

## Prioritization

When two initiatives compete, the order is: architectural prerequisite,
security importance, semantic importance, cross-subsystem leverage, public API
stability impact, technical risk, performance, developer experience.

Popularity is not on the list. Neither is feature count. Ten deeply integrated
primitives beat a hundred loosely connected features, and the second is easier
to build, which is exactly why it needs guarding against.

## The challenge process

Before any initiative moves from `RESEARCH` to `PLANNED`, it answers:

Why should Agnara own this? Why at this layer? Can a standard solve it? Can an
integration solve it instead? Does it introduce transport coupling? Does it put
state in the kernel? Does it create a god object? Does it weaken the capability
abstraction? Does it duplicate semantics that exist elsewhere? Can it be
compiled? Can it be introspected? Can it be secured? Can it be tested
independently?

An initiative that cannot answer these is not ready, however desirable it
sounds.
