# Target Architecture

This document describes where Agnara is going. Nothing here is a claim about
what exists — `docs/MATURITY.md` owns that, and every gap named below is
recorded there with a status.

It exists because several subsystems Agnara does not have yet would be
impossible to add later if today's kernel were built carelessly. Streaming,
durable tasks and capability composition all touch the execution model. The
point of writing them down now is not to build them now; it is to stop the
kernel from acquiring an assumption that forecloses them.

## 1. The thesis

Business capabilities are the product. Protocols are adapters.

```text
                        Capability
                            │
        ┌───────────┬───────┴───────┬───────────┐
        │           │               │           │
      HTTP         MCP             A2A       Events
        │           │               │           │
       CLI        Tasks          Direct     Streaming
```

Every surface reuses one capability definition, one schema, one dependency
graph, one authorization model, one risk and effect vocabulary, one execution
lifecycle, one failure vocabulary and one introspection model.

A protocol may constrain how a capability is *reached*. It must never become
the model of what a capability *is*. A capability's meaning cannot depend on
the transport that invoked it, or the promise above is false.

## 2. Small kernel, powerful adapters

"One framework" is a developer experience goal. It is not a packaging
strategy.

```text
agnara            the kernel: capability, schema port, DI, execution, policy,
                  introspection. Standard library only.
agnara-http       ASGI, routing, binding, OpenAPI, documentation, Explorer
agnara-mcp        MCP projection
agnara-a2a        A2A projection
agnara-events     event exposures and AsyncAPI projection
agnara-tasks      deferred, scheduled and durable execution contracts
agnara-telemetry  OpenTelemetry bridges
agnara-cli        scaffolding, introspection, diagnostics
agnara-testing    application test harness
```

The kernel keeps effectively zero third-party dependencies. An adapter may
depend on the protocol library it adapts. Nothing depends on a sibling
adapter — enforced today by `tests/architecture/test_package_boundaries.py`,
not by convention.

Anything that is an integration rather than a semantic — a database driver, a
cache, a broker, an LLM SDK — lives outside these packages entirely, behind a
contract the kernel defines and does not implement.

### Why not one package

A monolithic `agnara` would make every application pay for every protocol, and
would let a transport concern reach the kernel through an import that nobody
reviewed. The boundary is the mechanism that keeps the thesis in section 1
true under pressure.

## 3. The capability lifecycle

The end-state lifecycle, with today's status against each phase.

```text
declaration          IMPLEMENTED
registration         IMPLEMENTED
normalization        IMPLEMENTED   (metadata coercion at declaration)
schema compilation   IMPLEMENTED
dependency compile   IMPLEMENTED
policy compilation   IMPLEMENTED
exposure compilation  IMPLEMENTED  HTTP and MCP compile through one frozen, neutral availability registry
validation           IMPLEMENTED
freeze               IMPLEMENTED
startup              IMPLEMENTED
discovery            IMPLEMENTED
invocation           IMPLEMENTED
authorization        IMPLEMENTED
execution            IMPLEMENTED
streaming / result   PARTIAL       complete results and kernel streams; no transport stream projection
telemetry            IMPLEMENTED
audit                MISSING
cleanup              IMPLEMENTED   (DI teardown, invocation scope)
shutdown             PARTIAL       HTTP lifespan only; no task or consumer drain
```

### Invariants the lifecycle must keep

These hold today and must keep holding. Several already have architecture
tests; the ones that do not are named in `docs/INITIATIVES.md`.

1. **Compile once, execute many.** Reflection, schema construction, dependency
   traversal and policy interpretation happen before freeze, never per
   invocation.
2. **Immutable after freeze.** A compiled plan, registry or snapshot cannot be
   mutated. This is what makes free-threaded execution reachable later.
3. **No transport type crosses into a handler.** A capability never receives a
   request, session or connection object.
4. **Failure is canonical first.** A capability fails with a `FailureCode`; a
   transport maps that to its own representation. The reverse never happens.
5. **Cancellation is not a failure.** `CancelledError` propagates untranslated.
6. **Nothing published by accident.** Every introspection field is an explicit
   publication decision.
7. **Telemetry cannot change semantics.** A hook that raises must not alter the
   outcome of an invocation.

### Extension points

Phases an application may extend: schema adapters, dependency providers,
policies, telemetry hooks, exposures, documentation providers, visibility
rules.

Phases the runtime owns and must not open: compilation order, freeze,
the failure vocabulary, cancellation semantics, and the identity of a
capability. Opening any of these would let an extension change what a
capability means, which is the one thing adapters must never do.

## 4. Gap analysis

The systems the thesis requires and Agnara does not have. Ordered by how much
of the rest depends on them, not by size.

### G1 — Unified exposure model (resolved for the baseline)

ADR 0070 now gives HTTP and MCP one neutral compiled availability model, and
ADR 0071 builds the public HTTP composition API on it. A third adapter can
contribute a compiled surface without changing the kernel. Streaming and
future protocol-specific behavior remain separate gaps rather than reasons to
reopen this model.

*Former blockers removed:* public adapter composition and protocol-neutral
exposure introspection. Stability remains a later explicit decision.

### G2 — Streaming projections

The kernel now owns the stream lifetime and item contract (ADR 0084, ADR 0086):
declared async generators, explicit per-unit output schemas, pull-based demand,
cancellation, cleanup and post-output failure.
Adding wire projections independently would still produce incompatible
cancellation, backpressure and partial-failure semantics, so each projection
must preserve that contract rather than redefining it. HTTP SSE is implemented
against it and adds no stream vocabulary to core. It is designed in
ADR 0085 but is not implemented.

*Blocks:* SSE, WebSockets, MCP progress, A2A streaming, event consumption,
task progress.

### G3 — Execution identity and idempotency behaviour

Idempotency is declared and published but the runtime does nothing with it.
Deduplication, replay and safe retry all need an execution identity that
outlives a single invocation.

*Blocks:* durable tasks, event delivery semantics, safe automatic retry,
resilience integrations.

### G4 — Capability composition

A capability cannot call another capability with propagated principal,
deadline, cancellation, transaction and telemetry context. Applications will
work around this with direct function calls, which silently bypasses policy.

*Blocks:* workflows, sagas, any non-trivial application architecture.

### G5 — Durable execution

No task abstraction. Deferred, scheduled, long-running, retryable and
human-gated execution have no home, and every one of them needs G3.

### G6 — Audit

Telemetry answers "what happened, how fast". Audit answers "who was allowed to
do what, and on whose authority". Agnara has the second question's inputs —
principal, policy decision, effects, confirmation — and no system that records
them.

### G7 — Application testing

The repository tests the framework. It offers nothing to someone testing an
application built on it: no harness, no dependency overrides, no fake
principals, no policy or telemetry assertions.

*Blocks:* adoption more than architecture, but a framework that is hard to
test against will be used badly.

### G8 — Plugin and extension model

No discovery, loading, lifecycle, versioning or trust model. Defining it after
an ecosystem exists means defining it under compatibility constraints.

### G9 — Multi-tenancy

No tenant concept. Retrofitting one through DI, policies, caches, task queues
and telemetry is far harder than designing the propagation now.

### G10 — Public API stabilization

All 292 governed exports across 48 modules are deliberately classified
`provisional` (docs/PUBLIC_API.md). Before `1.0.0`, maintainers must make the
evidence-backed stable-or-deprecated compatibility decision; classification is
complete, stability is not implicit.

### G11 — Ecosystem interoperability

Agnara can be run and cannot be embedded. No contract says what an external
host must do to invoke a capability, and none says who owns lifecycle,
routing, dependency containers, context, principal, errors and telemetry when
two runtimes share a process.

The consequence is not a missing feature; it is that every application that
already exists must choose between adopting Agnara wholesale and not adopting
it. `docs/INTEROPERABILITY.md` states the contract this gap has to close and
RFC 0008 states the open questions.

*Blocks:* embedding, side-by-side composition, progressive adoption, and
`1.0.0` (ADR 0068).

## 5. Package roadmap

What each package is eventually responsible for, and what it must never own.

| Package | Owns | Must never own |
| --- | --- | --- |
| `agnara` | Capability semantics, schema port, DI, execution, policy, failures, introspection | Any protocol, server, schema library, LLM SDK, storage |
| `agnara-http` | ASGI, routing, binding, HTTP failure mapping, OpenAPI, documentation UIs, Explorer | Capability semantics, a sibling adapter |
| `agnara-mcp` | MCP projection, tools, MCP auth mapping, MCP error shapes | Redefining Agnara semantics in MCP terms |
| `agnara-a2a` | Agent Card, skill projection, A2A tasks and streaming | A separate execution engine |
| `agnara-events` | Event capability exposures, AsyncAPI projection, broker contracts | Any broker implementation |
| `agnara-tasks` | Task identity, state, retry, scheduling and persistence *contracts* | A worker runtime or a queue |
| `agnara-telemetry` | OpenTelemetry bridges | Deciding what is measured |
| `agnara-cli` | Scaffolding, introspection, diagnostics | Runtime behaviour |
| `agnara-testing` | Application test harness | Bypassing the runtime it tests |

## 6. Protocol roadmap

Each protocol is a one-way projection out of compiled semantics. A generated
contract is an output, never the source of truth.

```text
Capability + HTTP exposure   → OpenAPI 3.2
Capability + MCP exposure    → MCP discovery
Capability + A2A exposure    → Agent Card / skills
Event capability             → AsyncAPI
Capability graph             → Agnara introspection
```

**HTTP** — cookies, forms, multipart and uploads are implemented. The immediate
gap is streaming: SSE has an accepted design but no runtime, while WebSockets
need their own decision. Cross-cutting concerns remain deliberately outside the
adapter as outer ASGI middleware or server/proxy policy.

**MCP** — tools are projected; resources and prompts need a decision about
whether a capability maps to them coherently at all, rather than an
implementation. Progress and sessions depend on G2.

**A2A** — should be a projection over the same task and streaming primitives
as everything else. If A2A needs its own execution engine, the capability
runtime is wrong.

**Events** — the model is an event capability, not a broker client. Brokers
are integrations behind a contract.

**Standards first.** Where a standard exists, Agnara projects into it rather
than inventing a parallel vocabulary. A proprietary mechanism needs a recorded
technical reason.

## 7. What Agnara does not intend to be

Recorded so the question stops recurring.

- **Not an ORM.** Integration-first. A persistence contract may eventually
  standardize lifecycle, transactions and health; the data mapper stays
  external.
- **Not a broker, scheduler or worker runtime.** Agnara defines contracts;
  external systems implement them.
- **Not a frontend framework.** HTTP may return HTML. That is the whole
  commitment.
- **Not an admin UI.** Explorer is architecture and discovery tooling, and is
  optional in production.
- **Not an LLM framework.** No provider belongs in any Agnara package.
  Capabilities should be consumable *by* agent frameworks without Agnara
  choosing one.

The complement of this list is `docs/INTEROPERABILITY.md`. Declining to become
these systems only works if Agnara can cooperate with the ones that already
are — which is why the interoperability contract is part of the architecture
rather than a marketing concern.

## 8. North-star properties

The properties a future contributor should protect when a decision is
genuinely balanced.

One capability, defined once. One semantic model. Many surfaces, all
projections. No transport leakage into domain code. Compile once, execute
predictably. Security as a runtime concept rather than a middleware
convention. Machine-readable semantics for autonomous callers. Correlation on
every invocation. New protocols without redesigning the kernel. A small
kernel. Simple applications that stay simple.

When two designs offer equal power, the one with fewer concepts wins.
