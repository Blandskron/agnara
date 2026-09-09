# Roadmap

Where Agnara is going, in horizons.

This file owns *where Agnara is going*. `BACKLOG.md` owns what is ready to
implement, `docs/INITIATIVES.md` owns what to build in dependency order, and
`docs/MATURITY.md` owns what already exists. `docs/DOCUMENTATION_MAP.md`
records why each owns what it owns.

## No dates

A date without evidence is a fabrication. Agnara has no evidence about when
any of this will be done, so it commits to order rather than to time.

Work far beyond the current horizon is still recorded, because implementing
today's architecture wrongly would make some of it impossible later. That is
the reason to write it down — not to promise it.

## Horizons

Horizons are the ordering; a release is the thing that closes. The mapping is
fixed by ADR 0068 so that work lands where its question belongs rather than in
whichever release happens to be open.

### DONE — 0.1.0a4, Application Boundaries

Closed. Its question — can Agnara be consumed as a framework from outside this
repository? — was answered by the unified exposure model (ADR 0070), the public
HTTP composition surface (ADR 0071) and the HTTP request surface, all validated
against a clean-room external consumer.

Its *publication* did not close. One of fourteen artifacts reached PyPI; the
rest were rejected before upload. `0.1.0a4` is superseded by `0.1.0a5` and
should not be installed. ADR 0078.

### ABORTED — 0.1.0a5, Publication Recovery

The immutable `v0.1.0a5` tag exercised the corrected preflight. Publication
readiness stopped the workflow before the first upload because the seven
Trusted Publishers were still unverified. No `0.1.0a5` artifact was published.

### NOW — 0.1.0a6, Publication Recovery

Current baseline target, and deliberately small. It carries the `0.1.0a5`
runtime unchanged and asks the same question: can Agnara publish the set it
builds, completely, and prove that it did?

- **Publish readiness as a separate claim from code readiness.** ADR 0079.
- **Kernel published last**, so a partial publication fails closed.
- **Post-publication completeness verification**, gating the GitHub Release.
- **One source of truth for the seven distributions**, and a SHA-pinned
  publication path.

### NEXT — 0.1.0a7, Execution Semantics

Unchanged in content; moved one release later by ADR 0080. Its one question:
does execution have streaming, identity and a measured cost?

- **Streaming model** — `I2`, which still blocks the most other work.
- **Execution identity and idempotency behaviour.**
- **Performance budgets** — `I14`.

### BETA — 0.1.0b1, Interoperability

Its one question: can the Python ecosystem use Agnara, and Agnara use it?

- **Framework and ecosystem interoperability** — `I20`. Agnara standalone, as
  a host, embedded inside an existing framework, and side by side. RFC 0008
  states the questions and decides none of them.
- **Security program** — `I10`. Threat model, invariants with tests, supply
  chain.
- **A2A, events, audit, composition and testing utilities** — `I4`, `I5`,
  `I8`, `I12`, `I17`.
- **Durable execution** — `I6`, the abstraction rather than the workers.

### RC — 0.1.0rc1

No new subsystems. Regressions, documentation, compatibility, security,
packaging and release validation only.

### 1.0

- Stable execution, DI, policy, failure and introspection models.
- Stable HTTP composition API and MCP projection.
- Public API governance and deprecation policy in force.
  `docs/PUBLIC_API.md` owns the governed surface.
- **Free-threaded Python** verification — `I15`.

### POST-1.0

Distributed workers, a plugin and extension model (`I13`), workflow
orchestration (`I11`), multi-tenancy and federation (`I16`), and further
protocol adapters.

## What Agnara is not becoming

An ORM, a broker, a scheduler, a worker runtime, a frontend framework, an
admin UI, or an LLM framework. `docs/TARGET_ARCHITECTURE.md` section 7 records
why for each.

Agnara does not replace the ecosystem, so it has to be able to work with it
— alone, embedded, alongside, integrated.

## The governing trade

When features and architecture conflict, architecture wins. When a proprietary
mechanism and an open standard both work, the standard wins. When convenient
coupling and a clean boundary conflict, the boundary wins. When a large core
and a small kernel with strong adapters both work, the kernel stays small.
