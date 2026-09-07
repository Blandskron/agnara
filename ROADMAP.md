# Roadmap

Where Agnara is going, in horizons.

This file used to list Phase 0 through Phase 10 with no completion marks, so a
reader could not tell shipped from intended — and "Phase 0.5" had been
appended *after* Phase 10, which is what a document looks like when it has
stopped being maintained as a whole.

It no longer duplicates the backlog. Three documents were describing the same
future in three vocabularies:

- **what exists** → `docs/MATURITY.md`
- **what to build, in dependency order** → `docs/INITIATIVES.md`
- **what a release must satisfy** → `docs/releases/RELEASE_PLAN.md`

`docs/DOCUMENTATION_MAP.md` records why each owns what it owns.

## No dates

A date without evidence is a fabrication. Agnara has no evidence about when
any of this will be done, so it commits to order rather than to time.

Work far beyond the current horizon is still recorded, because implementing
today's architecture wrongly would make some of it impossible later. That is
the reason to write it down — not to promise it.

## Delivered

Verified against the code, not against this document. Per-subsystem detail and
its limits are in `docs/MATURITY.md`.

| | |
| --- | --- |
| **Capability kernel** | Declaration, metadata, identity, registry, startup freeze. |
| **Schema port** | Transport- and library-neutral, with a standard-library adapter. |
| **Dependency graph** | Compiled resolution, singleton and invocation scopes, generator teardown. |
| **Compiled execution** | Plans, policy stage, enforced deadlines, canonical failures, telemetry hooks. |
| **HTTP adapter** | ASGI, routing, binding, RFC 9457, OpenAPI 3.2, documentation providers, discovery, Explorer. Composition API still `EXPERIMENTAL`. |
| **MCP adapter** | Tool projection, invocation, schema mapping, authorization, result projection. |
| **Introspection** | Versioned protocol-neutral snapshot with per-field publication decisions. |
| **Telemetry** | OpenTelemetry metrics and span bridges over the core hook port. |
| **Project and app model** | `agnara project create` / `app create`, two architectures, exposure selection, profiles, aliases; apps own their capability namespace at runtime. |
| **Repository engineering** | Cross-platform CI, architecture tests, packaging gate, evidence-based release readiness. |

Three alphas are published. Only the `agnara` core distribution reaches PyPI.

## Which release owns what

Horizons are the ordering; a release is the thing that closes. The mapping is
fixed by ADR 0068 so that work lands where its question belongs rather than in
whichever release happens to be open.

| Release | Its one question |
| --- | --- |
| `0.1.0a4` | Can Agnara be consumed as a framework from outside this repository? |
| `0.1.0a5` | Does execution have streaming, identity and a measured cost? |
| `0.1.0b1` | Can the Python ecosystem use Agnara, and Agnara use it? |

A release with two theses proves neither, which is the whole reason the
mapping is written down.

## Horizons

### `NOW` — decide before building more

The two initiatives most other work waits on are both design-first, and both
are cheap to get wrong permanently.

- **I1 Unified exposure model.** HTTP and MCP each compile exposures their own
  way. Until there is one model, a third adapter invents a third mechanism and
  the public composition API cannot be settled — which is why `agnara-http`
  exports nothing today.
- **I2 Streaming model.** Nothing in the kernel returns a stream. Adding it
  per adapter would produce incompatible cancellation and backpressure
  semantics.
- **I9 Public API governance.** The seven governed core modules are
  classified; 23 more declare a public `__all__` that nothing classifies, and
  no API may be called stable until the deprecation policy exists.
  `docs/MATURITY.md` owns the status. This gets more expensive every release
  it is deferred.

### `NEXT ALPHA` — `0.1.0a4`, exposure and application boundaries

- **I7 HTTP request surface** — cookies, forms, multipart, uploads.
- **I1** implementation, once its RFC lands.

Not an integrations release. ADR 0068 records why, and what it may not
declare.

### `LATER ALPHA` — `0.1.0a5`, execution semantics

- **I3 Execution identity and idempotency behaviour.**
- **I2** implementation.
- **I14 Performance budgets** — baselines exist; a regression is currently
  invisible.

### `BETA` — `0.1.0b1`, interoperability and composition

- **I20 Framework and ecosystem interoperability** — the release's thesis.
  Agnara standalone, as a host, embedded inside an existing framework, and
  side by side with one. `docs/INTEROPERABILITY.md` owns the contract and the
  integration matrix; RFC 0008 holds the open questions.
- **I10 Security program** — threat model, invariants with tests, supply
  chain. `SECURITY.md` already records these as absent.
- **I4 A2A**, **I5 Events**, **I17 Audit**, **I8 Composition**,
  **I12 Testing utilities**.
- **I6 Durable execution** — the abstraction, not the workers.

### `1.0`

Criteria live in `docs/releases/RELEASE_PLAN.md`. In summary: the capability,
execution, DI, policy, failure and introspection models are stable; the HTTP
composition API is public; the MCP projection is stable; a security review has
happened; performance budgets exist; public API governance is in force; the
deprecation policy is written.

- **I15 Free-threaded Python** verification.

### `POST-1.0`

- **I6** distributed workers, **I13 Plugin model**, **I16 Multi-tenancy**,
  federation, further protocol adapters.

### `RESEARCH`

Open questions, listed in `docs/INITIATIVES.md` so they are not mistaken for
plans: workflow ownership, remote capability consumption, cost metadata, data
classification, GraphQL and gRPC projections, framework-level i18n, a second
shipped schema adapter.

## What Agnara is not becoming

An ORM, a broker, a scheduler, a worker runtime, a frontend framework, an
admin UI, or an LLM framework. `docs/TARGET_ARCHITECTURE.md` section 7 records
why for each, so the question stops recurring.

The corollary is `docs/INTEROPERABILITY.md`: Agnara does not replace the
ecosystem, so it has to be able to work with it — alone, embedded, alongside,
integrated.

## The governing trade

When features and architecture conflict, architecture wins. When a proprietary
mechanism and an open standard both work, the standard wins. When convenient
coupling and a clean boundary conflict, the boundary wins. When a large core
and a small kernel with strong adapters both work, the kernel stays small.

The objective is not more functionality than other frameworks. It is more
coherent power from fewer concepts.
