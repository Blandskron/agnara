# ADR 0068 — Interoperability Release Ownership

- Status: Proposed
- Date: 2026-09-07
- Initiative: I20 Framework and ecosystem interoperability
- Tracking: GitHub Issue #282
- Related: ADR 0003, ADR 0021, RFC 0006, RFC 0008

## Context

Framework and ecosystem interoperability — FastAPI, Django, Flask, Litestar,
Starlette, SQLAlchemy, PostgreSQL, Pydantic, Jinja2, Celery, Redis,
OpenTelemetry — is the work that decides whether Agnara is adoptable by
applications that already exist. `docs/INTEROPERABILITY.md` states the
principle and the matrix; RFC 0008 states the open design questions.

That work has no release. Without one it will arrive in whichever release is
open when someone needs it, which in practice means the next one. The pressure
is real and predictable: the `0.1.0a4` gates ask whether Agnara can be consumed
from outside the repository, and the shortest path to a green gate is to add a
FastAPI integration and call the question answered.

That would be the wrong answer to the right question. `0.1.0a4` asks whether
the *public API* is sufficient to build an application. An integration that
hides an insufficient API behind a framework-specific convenience makes the
gate green and the finding disappear.

There is also a second, quieter pressure. `0.1.0a5` does not exist in
`docs/releases/RELEASE_PLAN.md` today; the path goes `0.1.0a4` → `0.1.0b1`.
That leaves streaming (I2), execution identity and idempotency (I3) and
performance budgets (I14) — all `LATER ALPHA` in `docs/INITIATIVES.md` — with
no release that owns them, so they fall into either the release before or the
release after. Both placements are wrong: `0.1.0a4` becomes two releases, or
`0.1.0b1` becomes three.

## Decision

### The alpha line gains `0.1.0a5`

The path becomes:

```text
0.1.0a4  →  0.1.0a5  →  0.1.0b1  →  0.1.0rc1  →  0.1.0
```

`docs/releases/RELEASE_PLAN.md` owns the gates for each. This ADR fixes only
what each release is *for*, because that is the part that decides where work
lands when it is ambiguous.

### `0.1.0a4` — Application Alpha

Owns the foundations that make interoperability possible later: the unified
exposure model (I1), the HTTP request surface (I7), a public
exposure and composition surface, and the boundaries an adapter will need.

Its existing gates are unchanged. Its question stays "can Agnara be consumed as
a framework rather than exercised internally", and the answer must come from
applications that use the public API, not from a framework integration that
routes around it.

### `0.1.0a5` — Execution Alpha

Owns the streaming model (I2), execution identity and idempotency behaviour
(I3), performance budgets (I14), and the technical prerequisites already
recorded for those initiatives.

### `0.1.0b1` — Interoperability and Composition Beta

Owns framework and ecosystem interoperability: hosting external
infrastructure, running embedded inside an existing framework, composing side
by side in one process, exposing capabilities through replaceable adapters, and
progressive adoption by an application that will not be rewritten.

It keeps its existing beta gates. It gains interoperability gates, because a
beta that declares a public contract without demonstrating that the ecosystem
can use it has declared a contract nobody has tested.

Implementation starts when the `0.1.0a4` and `0.1.0a5` prerequisites those
integrations depend on are complete — RFC 0008 section 6 lists which
integration needs which.

### Guardrails

**`0.1.0a4` must not become** a FastAPI release, a Django release, a
SQLAlchemy release, or an interoperability release. It may run small
experiments where they validate I1 — an experiment is `experiments/`, unpinned,
undocumented as a feature, and named in no release note as support.

**`0.1.0a5` must not become** an ecosystem integration release, a composition
beta, or a plugin marketplace. It may use an integration as an experimental
fixture where that helps validate streaming, idempotency or performance, and
must not publish the fixture as a contract.

**Neither may declare stable support** for any external framework. `EXPERIMENTAL`
in `docs/MATURITY.md` is the strongest status either release may give an
integration.

### Changing a gate

If research shows one of the `0.1.0b1` interoperability gates is wrong — the
wrong technology, the wrong direction, the wrong bar — it is changed through an
ADR or RFC carrying the evidence. It is never quietly dropped, relaxed, or
marked non-mandatory during release preparation, which is exactly when the
pressure to do so peaks.

## Consequences

**Positive.** Each release has one question. Interoperability gets a home
before it needs one, so the decision is made calmly rather than under gate
pressure. The alpha line stops carrying work it cannot finish. RFC 0008 can be
answered against real prerequisites instead of guesses.

**Negative.** The alpha line is longer by one release, and `0.1.0b1` is further
away in sequence. Both are honest: the work was always there, and moving it
earlier in the document would not have moved it earlier in reality.

**Accepted risk.** An application may want FastAPI support before `0.1.0b1`.
The answer is an application-owned integration against the public API, not a
first-party one built early. If the public API is not sufficient to write that
integration, that is a `0.1.0a4` finding and exactly the kind this ADR exists
to keep visible.

## Alternatives considered

**Put interoperability in `0.1.0a4`.** Rejected: it hides the `0.1.0a4`
finding behind a convenience layer, and it designs an embedding contract on an
unsettled exposure model (RFC 0006).

**Leave it undated in `POST-1.0`.** Rejected: it would then be built
opportunistically, one framework at a time, each shaping the boundary the next
one has to live with. The anti-coupling test in `docs/INTEROPERABILITY.md`
section 5 is unenforceable against work with no release that owns it.

**No `0.1.0a5`; fold I2, I3 and I14 into `0.1.0b1`.** Rejected: `0.1.0b1` would
then have to prove streaming, identity, performance *and* interoperability, and
a release with four theses proves none of them.
