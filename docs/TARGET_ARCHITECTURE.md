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

## 4. Current boundaries and open work

The shipped runtime already has a unified exposure model (ADR 0070), a
classified stable public API (`docs/PUBLIC_API.md`), declared streaming output
with HTTP SSE (ADR 0084–0086), execution identity, direct complete-result
idempotency, and bounded same-snapshot nested composition (ADR 0093).
Framework-neutral embedding is implemented through ADR 0094; version-pinned
host fixtures validate selected integrations. These contracts remain distinct
from their future extensions.

### Streaming and protocol projections

The core owns pull demand, cancellation, cleanup, per-unit validation and
terminal outcomes. HTTP SSE projects this contract. WebSockets, MCP progress,
A2A streaming, event consumption, request-body streaming and replay are not
supported without separate design and conformance evidence.

### Durable execution and persistence

In-memory idempotency is process-local. There is no durable task scheduler,
retry service or automatic effect recovery. Applications own their storage,
transactions and any durable idempotency implementation.

### Delegation and cross-application composition

Nested invocation rechecks the caller's authority and enforces depth limits.
Delegation of additional authority and cross-application composition are
refused. RFC 0005 and RFC 0008 contain the remaining design questions.

### Ecosystem support

Standalone, hosted, embedded and side-by-side modes share a value-only
contract. Starlette, FastAPI, Django, Litestar, SQLAlchemy/SQLite and
OpenTelemetry fixtures provide bounded evidence; broader framework support
needs reviewed versioned conformance. `docs/INTEROPERABILITY.md` owns the
current matrix.

### Other research

An application testing harness, audit persistence, plugin discovery,
multi-tenancy and Python 3.15 support require separate decisions. No current
release claim depends on implementing them.

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

**HTTP** — cookies, forms, multipart, uploads and the bounded SSE streaming
projection are implemented. WebSockets still need their own decision.
Cross-cutting concerns remain deliberately outside the adapter as outer ASGI
middleware or server/proxy policy.

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
