# Interoperability and Composition

How Agnara relates to the rest of the Python ecosystem, and what `1.0.0` has
to demonstrate before that relationship can be called a contract.

This document owns the **interoperability contract and the integration
matrix**. It does not own status (`docs/MATURITY.md`), order
(`docs/INITIATIVES.md`) or release gates (`docs/releases/RELEASE_PLAN.md`).
Where it appears to restate one of those, the other document wins.

Nothing here is a claim that an integration exists. At the time of writing none
of them does: no Agnara package imports a web framework, an ORM, a broker or a
template engine, and that is the property this document is written to protect
while the integrations are designed.

## 1. The principle

> **Agnara must not require ownership of the entire application stack.**

A framework earns adoption by being addable, not by being total. An application
that already has FastAPI routes, Django models, SQLAlchemy sessions, Celery
workers and an OpenTelemetry pipeline should be able to turn *one* business
operation into an Agnara capability without changing any of them, and without a
rewrite it has no reason to fund.

This is the argument `docs/TARGET_ARCHITECTURE.md` section 1 makes about
protocols, applied one level out: a protocol constrains how a capability is
*reached* and never defines what it *is*; a framework constrains how a process
is *hosted* and likewise never defines what a capability is.

## 2. The four modes

Agnara must remain usable in all four. They are not stages of maturity; they
are four legitimate deployments, and a design that makes any of them impossible
is wrong.

### Mode 1 — Standalone

```text
Agnara
   ↓
Application
```

Agnara owns the process. No external framework is present. This is the mode the
repository exercises today, and it must keep working with the core distribution
alone.

### Mode 2 — Agnara as host

```text
Agnara
   ↓
External infrastructure or framework
```

Agnara owns the process and reaches outward through ports: a database, a cache,
a broker, a template engine, a telemetry pipeline. Agnara decides lifecycle;
the external system keeps its own semantics.

### Mode 3 — Agnara embedded

```text
Existing framework or application
          ↓
       Agnara
```

Something else owns the process, the routing table, the middleware chain and
the request lifecycle. Agnara is invoked from inside it, and owns capability
semantics and nothing else.

### Mode 4 — Side-by-side composition

```text
Existing framework ─┐
                    ├── same application / process
Agnara exposures ───┘
```

Native routes and Agnara exposures serve from one process, sharing a lifespan
and a telemetry pipeline without duplicating either.

All four are expressible in ports-and-adapters as it already exists
(`ARCHITECTURE.md` sections 3, 4 and 9). Mode 2 is an outbound port with an
adapter. Mode 3 is an inbound adapter that happens to be written by the host
rather than by Agnara. Mode 4 is two inbound adapters over one compiled
application. No new architectural style is required, which is the strongest
available evidence that the existing boundaries were drawn in the right place.

## 3. The two directions

Every integration is analysed in two directions, and the answer is frequently
asymmetric. Forcing symmetry produces adapters nobody wants.

| Direction | Shape | Question it answers |
| --- | --- | --- |
| **Agnara + X** | Agnara hosts; X is infrastructure behind a port | Can Agnara use the ecosystem? |
| **Agnara inside X** | X hosts; Agnara is invoked | Can the ecosystem use Agnara? |

```text
A. Agnara + X                    B. Agnara inside X

   Agnara                            FastAPI
      ↓                                 ↓
   ASGI / SQLAlchemy adapter         Agnara capability
      ↓                                 ↓
   server / PostgreSQL               Agnara runtime
```

Where one direction is meaningless it is recorded as **discarded**, with the
reason. "SQLAlchemy hosts Agnara" is not a modest goal; it is not a goal at
all, and saying so is more useful than an empty cell.

## 4. Kernel invariants

The properties every future integration is measured against. They restate and
extend the core invariants in `AGENTS.md` and `ARCHITECTURE.md` section 3;
where this list and those disagree, those win.

1. `agnara` remains transport-neutral (ADR 0003).
2. `agnara` remains framework-neutral. No web, ORM, broker, template, schema or
   telemetry library becomes a kernel dependency — ever, not merely not yet.
3. Every external framework is optional. Removing all of them leaves a working
   framework.
4. A business handler never receives a raw framework object by default.
5. An external request, session, connection or transaction object never crosses
   into the kernel.
6. Framework context enters only through an explicit bridge, declared by the
   integration and visible in application code.
7. A canonical Agnara result stays protocol- and framework-neutral (ADR 0022).
8. Integration-specific errors are translated at the boundary that owns them,
   never propagated inward. ADR 0028 shows the shape for HTTP.
9. Resource ownership is explicit: exactly one side creates, and the same side
   destroys.
10. Lifecycle ownership is explicit: exactly one side owns startup and shutdown
    order.
11. Dependency-injection scope semantics stay Agnara-defined. A host's request
    scope maps *onto* an invocation scope; it does not replace it.
12. Telemetry stays framework-neutral. A span's meaning cannot depend on who
    called the capability (ADR 0055, ADR 0056).
13. One integration never dictates another's architecture. The second adapter
    for a port is the test of the first.
14. Progressive adoption stays possible. No integration may require
    all-or-nothing migration.
15. Agnara still works standalone with no external framework present.

Invariants 1 and 2 are partly machine-enforced by
`tests/architecture/test_package_boundaries.py`, which fails when the kernel
imports anything outside the standard library and names the specific forbidden
dependency when it is one of the technologies below.

## 5. The anti-coupling test

Two questions, asked of every proposal, before design and again before merge.

> **If this integration were removed tomorrow, would `agnara` still make
> architectural sense?**

If no, the integration is contaminating the kernel.

> **Could a second framework implement the same port without changing the
> kernel?**

If no, the boundary is shaped around the first framework rather than around the
problem.

An integration that fails either question is redesigned or declined. It is
never merged with a note promising to generalize it later; the note never
survives contact with the second framework.

## 6. Integration matrix

The research and future-conformance inventory. **Priority** is architectural
importance, not popularity. The authoritative release bar remains the gate
table in `docs/releases/RELEASE_PLAN.md`; this matrix selects useful evidence
scenarios without creating a second source of release authorization.

Legend: `yes` — a coherent, intended direction; `no` — deliberately discarded,
reason in the notes; `partial` — coherent for part of the technology only.
`1.0.0 evidence` identifies scenarios that can contribute evidence to the
release-plan interoperability gate; it is not a second release gate or an
authorization to claim support.

### Web, ASGI and WSGI

| Technology | Agnara as host | Agnara embedded | Side-by-side | Priority | 1.0.0 evidence | Notes |
| --- | :---: | :---: | :---: | --- | :---: | --- |
| Starlette | yes | yes | yes | CRITICAL | yes | The clean-room ASGI proof. Mounting, ASGI composition, request context, response mapping, middleware, lifespan and error boundaries, without FastAPI-specific behaviour confusing the result. |
| FastAPI | yes | yes | yes | CRITICAL | yes | The highest-value adoption path. Progressive adoption inside an existing FastAPI application is the priority scenario, not a bonus. |
| Django | partial | yes | yes | CRITICAL | yes | The host direction covers Django *infrastructure* — ORM, auth, templates — not Django's routing or process model. Agnara never replaces the ORM, Admin, Auth or Templates; it cooperates with them. |
| Django REST Framework | no | yes | yes | HIGH | no | Embedding into existing DRF APIs. Hosting DRF is meaningless: DRF is a view layer inside Django. |
| Django Ninja | no | yes | yes | MEDIUM | no | Secondary confirmation that the Django embedding contract is not DRF-shaped. |
| Flask | no | yes | research | HIGH | no | Embedding and the migration path matter. Hosting Flask does not: Agnara's HTTP boundary is ASGI (ADR 0041), and a WSGI host bridge belongs on the Flask side. Agnara must not adopt WSGI semantics in the core. |
| Litestar | yes | yes | yes | HIGH | conditional | The fourth web gate is satisfied by Flask **or** Litestar. Validates ASGI, DI coexistence, lifecycle, routing, serialization, middleware and embedding. |
| Falcon | no | yes | research | MEDIUM | no | Kept only while it produces new evidence about WSGI/ASGI independence. |
| aiohttp | no | yes | research | MEDIUM | no | Low-level async interoperability outside the ASGI ecosystem. |
| Sanic, Quart | no | research | research | LOW | no | Research. They block `1.0.0` only if they reveal an architectural problem the others hid. |
| Robyn | research | research | research | LOW | no | Research. |

### Data and persistence

Agnara is not becoming an ORM. The goal is to prove it can use the one the
application already has.

| Technology | Agnara as host | Agnara embedded | Side-by-side | Priority | 1.0.0 evidence | Notes |
| --- | :---: | :---: | :---: | --- | :---: | --- |
| SQLite | yes | n/a | n/a | CRITICAL | yes | The baseline that needs no external infrastructure. Capability → provider → repository → SQLite, validating connection lifecycle, transactions, rollback, invocation scope, cleanup and testability. |
| PostgreSQL | yes | n/a | n/a | CRITICAL | yes | Pooling, transaction scope, concurrent execution, async where it applies, rollback, failure handling, startup and shutdown, resource cleanup. |
| SQLAlchemy | yes | no | n/a | CRITICAL | yes | The primary persistence integration, over both SQLite and PostgreSQL. Engine lifecycle, `Session`, `AsyncSession`, DI scopes, unit of work, commit, rollback, nested execution, teardown. Agnara reimplements none of these. |
| psycopg | yes | no | n/a | HIGH | no | PostgreSQL without an ORM, proving the persistence port is not SQLAlchemy-shaped. |
| asyncpg | yes | no | n/a | MEDIUM | no | Async database provider validation. |
| Alembic | coexist | n/a | yes | HIGH | no | Migrations must coexist with an Agnara application unchanged. Agnara never gets its own migration system. |
| SQLModel | yes | no | n/a | MEDIUM | no | Interesting only where SQLAlchemy and Pydantic meet. |
| MySQL, MariaDB | yes | n/a | n/a | MEDIUM | no | Evidence that the persistence work is not PostgreSQL-specific. No dedicated historical reference needed. |

### Schema and models

The core stays library-neutral (ADR 0004). The standard-library adapter is the
baseline and ships today.

| Technology | Agnara as host | Agnara embedded | Side-by-side | Priority | 1.0.0 evidence | Notes |
| --- | :---: | :---: | :---: | --- | :---: | --- |
| `dataclasses` | yes | n/a | n/a | BASELINE | yes | Already `IMPLEMENTED`. Nothing may make it the second-class path. |
| Pydantic | yes | n/a | n/a | CRITICAL | yes | A formal `SchemaAdapter`: input models, output models, nesting, the validation boundary, JSON Schema, error translation, serialization. Never a kernel dependency. |
| msgspec | yes | n/a | n/a | HIGH | yes, if ready | The evidence that `SchemaAdapter` was not designed around Pydantic. Whether the port needs a second *shipped* adapter is its own open question in `docs/INITIATIVES.md`. |

### Presentation

Agnara is not becoming a frontend framework. HTTP may return HTML; that is the
whole commitment (`docs/TARGET_ARCHITECTURE.md` section 7).

| Technology | Agnara as host | Agnara embedded | Side-by-side | Priority | 1.0.0 evidence | Notes |
| --- | :---: | :---: | :---: | --- | :---: | --- |
| Jinja2 | yes | n/a | yes | HIGH | yes, or equivalent | HTTP → capability → application data → template → HTML. Template context, a safe rendering boundary, response integration, and forms once I7 lands. |
| Django templates | partial | yes | yes | MEDIUM | no | Validated inside a Django application, not as a standalone integration. |
| HTMX | n/a | n/a | yes | MEDIUM | no | Partial-HTML responses must be expressible without an SPA. No HTMX-specific API enters any Agnara package. |

### Background execution

Agnara is not becoming a broker, scheduler or worker runtime. It integrates
them.

| Technology | Agnara as host | Agnara embedded | Side-by-side | Priority | 1.0.0 evidence | Notes |
| --- | :---: | :---: | :---: | --- | :---: | --- |
| Celery | yes | yes | yes | HIGH | yes, or one equivalent | Capability → task adapter → Celery → broker → worker → Agnara invocation. Must resolve serialization, execution identity, principal propagation, deadlines, retries, idempotency, failures, telemetry and capability lookup. A Celery retry is not an Agnara execution semantic and must never be confused for one. |
| Taskiq | yes | yes | yes | MEDIUM | no | Modern async alternative; the second implementation that tests the task port. |
| Dramatiq | yes | yes | yes | MEDIUM | no | |
| RQ | yes | yes | yes | LOW | no | Does not block `1.0.0`. |

### Messaging

| Technology | Agnara as host | Agnara embedded | Side-by-side | Priority | 1.0.0 evidence | Notes |
| --- | :---: | :---: | :---: | --- | :---: | --- |
| Redis | yes | n/a | yes | HIGH | yes, with Celery | Cache, task backend, ephemeral state, coordination. Never part of the kernel. |
| RabbitMQ | yes | n/a | yes | HIGH | alternative to Redis | Task and event transport. |
| Kafka | yes | n/a | yes | HIGH / FUTURE | no | Event-driven capabilities; depends on I5. |
| NATS | yes | n/a | yes | HIGH / FUTURE | no | Lightweight modern messaging; depends on I5. |

### Durable execution

| Technology | Agnara as host | Agnara embedded | Side-by-side | Priority | 1.0.0 evidence | Notes |
| --- | :---: | :---: | :---: | --- | :---: | --- |
| Temporal | yes | yes | n/a | HIGH | no | Depends on I6. Agnara contributes capability contracts, policies, identity, effects, risk, authorization and discovery; Temporal contributes durability, retries, workflow state, worker execution and recovery. The frontier stays explicit, and no proprietary workflow engine is built while a clean integration can answer the question. |
| Prefect | yes | yes | n/a | MEDIUM | no | Data orchestration. A Prefect flow is not an Agnara capability and the two vocabularies must not be merged. |

### Observability

| Technology | Agnara as host | Agnara embedded | Side-by-side | Priority | 1.0.0 evidence | Notes |
| --- | :---: | :---: | :---: | --- | :---: | --- |
| OpenTelemetry | yes | yes | yes | CRITICAL | yes | Bridges exist (ADR 0054 through ADR 0058); `1.0.0` validates them end to end — traces, spans, metrics, propagation, invocation and execution identity across HTTP, workers, databases and errors. The SDK never enters `agnara`. |
| Sentry | yes | yes | yes | MEDIUM | no | Through an adapter or integration layer. Never an official dependency. |

### Agent and protocol interoperability

| Technology | Agnara as host | Agnara embedded | Side-by-side | Priority | 1.0.0 evidence | Notes |
| --- | :---: | :---: | :---: | --- | :---: | --- |
| MCP | yes | yes | yes | CRITICAL | yes | Already implemented for tools. `1.0.0` proves HTTP and MCP project the *same* capability with no duplicated business logic, including from inside an embedded host. |
| A2A | yes | yes | yes | HIGH | no | Enters when I4 is ready. Capabilities participate in agent-to-agent communication without kernel change, or the exposure model is wrong. |

### Command line

| Technology | Agnara as host | Agnara embedded | Side-by-side | Priority | 1.0.0 evidence | Notes |
| --- | :---: | :---: | :---: | --- | :---: | --- |
| Typer, Click, `argparse` | yes | yes | yes | HIGH | no | Target: one capability reachable over HTTP, MCP and a CLI with no duplicated business logic. `agnara-cli` owns scaffolding and introspection (`ARCHITECTURE.md` section 15); an application's own CLI is an integration, not a CLI framework chosen on the user's behalf. |

### Under research, with no `1.0.0` commitment

| Technology | Priority | Notes |
| --- | --- | --- |
| GraphQL (Strawberry, Graphene) | RESEARCH | A capability → GraphQL projection needs an approved RFC before it is a commitment. Already an open research question in `docs/INITIATIVES.md`. |
| gRPC | RESEARCH | Projection and adapter architecture only. |

## 7. The framework embedding contract

The minimum an external host needs in order to invoke Agnara. It must be small,
framework-neutral and stable enough that FastAPI, Django, Flask, Litestar and
Starlette all use the same one.

```text
Host framework
     │
     │  1. obtain the compiled application / runtime
     │  2. look up a capability by id
     │  3. create an invocation
     │  4. provide context
     │  5. propagate principal
     │  6. pass a deadline
     │  7. execute
     │  8. receive a canonical result
     │  9. map errors into host terms
     │ 10. observe telemetry
     ↓
Agnara runtime
```

Each step is a question RFC 0008 has to answer, not an API this document
invents. Two constraints are already fixed by existing decisions and are not
open:

- the host never hands a request, session or connection object to a capability
  (invariants 4 and 5, ADR 0026);
- the result the host receives is canonical and the host maps it, rather than
  Agnara producing a host-shaped result (invariant 7, ADR 0022).

## 8. The infrastructure adapter contract

How Agnara uses external infrastructure without knowing which implementation is
behind it. The categories:

```text
database        cache          broker        telemetry
schema          transport      task runtime  durable execution
templates
```

There is deliberately **no universal adapter**. A cache and a durable execution
engine do not share a lifecycle, a failure model or a consistency story, and a
single interface over both would fit neither. Each category gets its own port,
with only the genuinely shared concerns — lifecycle, scope, failure
translation, telemetry, cleanup — expressed the same way across them.

The kernel defines the port and does not implement it
(`docs/TARGET_ARCHITECTURE.md` section 2). An implementation lives in an
integration package, an optional dependency group, or the application itself.

## 9. The conformance suite

An adapter is not "integrated" because a demo runs. It is integrated when it
passes one shared scenario, which is the same scenario for every framework:

```text
declare capability
      ↓
compile
      ↓
external framework invokes
      ↓
context created
      ↓
dependencies resolved
      ↓
policy evaluated
      ↓
handler executed
      ↓
result translated
      ↓
telemetry emitted
      ↓
resources cleaned up
```

Each adapter demonstrates the dimensions that apply to it.

| Dimension | What it proves |
| --- | --- |
| startup / shutdown | Lifecycle ownership is explicit and ordered. |
| lifecycle | The host's lifespan and Agnara's compile and freeze do not fight. |
| sync and async | Neither is a second-class path. |
| cancellation | `CancelledError` still propagates untranslated. |
| context propagation | Correlation survives the boundary in both directions. |
| dependency scopes | A host request scope maps onto an invocation scope. |
| validation | The schema boundary is the one direct invocation already uses. |
| error mapping | Canonical failures translate at the boundary, not before it. |
| serialization | The wire shape is the adapter's; the value is Agnara's. |
| security | Policy is evaluated, and the host path cannot skip it. |
| telemetry | One span tree, not two. |
| cleanup | No leaked connection, session, task or scope. |

**Generic before specific.** Where a generic contract can express a
requirement, no framework-specific API is added for it. The suite is what makes
that rule checkable: a dimension that can only be expressed per framework is
evidence that the contract is missing something.

The suite's own home — `agnara-testing` (I12), a repository test tier, or a
separate conformance repository — is an open question in RFC 0008.

## 10. Side-by-side composition

An explicit `1.0.0` objective, and the mode most likely to expose a design
error, because it is where two lifecycles meet.

```text
FastAPI application
├── native FastAPI endpoints
├── mounted Agnara exposures
└── endpoints invoking Agnara capabilities directly
```

It must be possible without:

- duplicating the lifecycle;
- corrupting the host's middleware chain;
- breaking context propagation in either direction;
- creating two containers that disagree about a dependency;
- emitting the same telemetry twice;
- requiring dangerous global state to find the runtime.

The last one is the trap. "Just use a module-level singleton" makes the first
demo work and makes two applications in one process impossible — which is what
invariant 13 and the multiple-application question in RFC 0008 exist to
prevent.

## 11. Progressive adoption

A strategic requirement, not a convenience.

```text
Existing application
        ↓
introduce the Agnara runtime
        ↓
one business operation becomes a capability
        ↓
more operations migrate, on the application's schedule
```

No step may require the previous one to be finished everywhere. Validated
specifically against FastAPI, Django and Flask, because those are the
applications that exist.

An adoption path that requires a rewrite is not an adoption path. It is a
migration project, and most of them are never funded.

## 12. What Agnara is not becoming

Recorded in `docs/TARGET_ARCHITECTURE.md` section 7, and repeated here only as
the list an integration proposal is checked against:

ORM · migration framework · database driver · template engine · frontend
framework · message broker · task queue · scheduler · worker runtime ·
distributed tracing backend · workflow runtime · authentication database ·
admin interface.

Where a mature ecosystem solution exists, Agnara integrates with it across a
clean boundary. The reason is not modesty: every one of those systems is better
at being itself than a framework subsystem would be, and owning a worse version
of one costs the kernel its size.

## 13. Validation order

The order implementation follows while `1.0.0` is built. It changes only for a
demonstrated technical dependency, and the change is recorded.

```text
 1. Starlette                      9. msgspec
 2. FastAPI                       10. Jinja2
 3. SQLAlchemy + SQLite           11. Celery
 4. PostgreSQL                    12. Redis / RabbitMQ
 5. Django                        13. OpenTelemetry end to end
 6. Litestar                      14. MCP + HTTP shared capability
 7. Flask                         15. research integrations
 8. Pydantic
```

Starlette is first deliberately. It is the smallest host that can exercise the
whole embedding contract, so a defect it finds is a defect in the contract
rather than in FastAPI's interpretation of it.

## 14. Historical reference strategy

No historical reference application is created for any of these integrations
now. A historical reference freezes a public surface, and freezing an
experimental one converts an experiment into a contract nobody agreed to.

For `1.0.0`, references are grouped by **architecture, not by
library**, so that adding a fourth ASGI framework does not mean a fourth
repository:

```text
agnara-asgi-interoperability      agnara-data-interoperability
├── Starlette                     ├── SQLAlchemy
├── FastAPI                       ├── SQLite
└── Litestar                      └── PostgreSQL

agnara-django-interoperability    agnara-schema-interoperability
├── Django hosts Agnara           ├── dataclasses
├── Django ORM                    ├── Pydantic
├── auth                          └── msgspec
└── templates
                                  agnara-background-execution
                                  ├── Celery
                                  └── Redis / RabbitMQ
```

## 15. Related

- `PRINCIPLES.md` — the rules a decision must not break
- `ARCHITECTURE.md` — the boundaries as they exist today
- `docs/TARGET_ARCHITECTURE.md` — where the structure is going
- `docs/INITIATIVES.md` — I20, and the order this work happens in
- `docs/releases/RELEASE_PLAN.md` — the `1.0.0` gates
- `docs/rfc/0008-framework-embedding-and-ecosystem-composition.md` — the open
  design questions
- `docs/adr/0068-interoperability-release-ownership.md` — why this belongs to
  `1.0.0`
