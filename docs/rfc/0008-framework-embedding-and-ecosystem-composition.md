# RFC 0008 — Framework Embedding and Ecosystem Composition

- Status: Proposed
- Date: 2026-09-07
- Tracking: GitHub Issue #282
- Initiative: I20
- Supersedes: nothing
- Related: RFC 0006 (unified exposure model), RFC 0005 (protocol-neutral
  delegation), ADR 0003, ADR 0022, ADR 0026, ADR 0041, ADR 0068

## 1. Summary

Agnara can be run. It cannot yet be *embedded*, *hosted alongside*, or
*adopted incrementally* by an application that already exists, because no
contract says what an external host must do in order to invoke a capability,
and no contract says who owns lifecycle, routing, dependency containers,
context, errors and telemetry when two runtimes share one process.

This RFC states those questions. It decides none of them. Several depend on
RFC 0006 and on initiatives that are not finished, and answering them now would
mean inventing an implementation on top of an unsettled exposure model —
exactly the mistake `docs/INITIATIVES.md` records as the reason I1 exists.

The answers become one or more ADRs, and the implementation belongs to
`0.1.0b1` (ADR 0068).

## 2. Context

`docs/INTEROPERABILITY.md` states the principle: Agnara must not require
ownership of the entire application stack, and must work standalone, as a host,
embedded, and side by side.

Three of those four modes have no contract.

**Standalone works.** The repository exercises it.

**Agnara as host** partly works: dependency providers already let an
application reach a database or a cache, and `agnara-telemetry` already bridges
to OpenTelemetry. What is missing is a stated contract for lifecycle and
ownership per infrastructure category, so every application invents its own.

**Agnara embedded** has no contract at all. An external host would have to
import private modules — the same problem `the release status` records as
a `0.1.0a4` blocker, one level further out.

**Side-by-side** has no contract, and is where the design errors hide: two
lifecycles, two containers, two telemetry pipelines, one process.

The architecture is favourable. Ports and adapters are already the style
(`ARCHITECTURE.md` sections 3 and 4), the kernel already imports nothing but
the standard library, failures are already canonical (ADR 0022), the ASGI
boundary is already explicit (ADR 0041), and no transport type reaches a
handler (ADR 0026). None of that is an accident, and none of it is the same
thing as a contract an external framework can code against.

## 3. Scope

**In scope:** the embedding contract, the ownership questions that arise when
Agnara shares a process, and the shape of the infrastructure adapter contract.

**Out of scope:** any specific framework integration. FastAPI, Django, Flask,
SQLAlchemy and Celery appear below as forcing functions on the design, never as
deliverables of this RFC. Adding one as a dependency to demonstrate a plan is
explicitly forbidden.

**Also out of scope:** the exposure model itself. RFC 0006 owns it, and this
RFC assumes whatever it decides.

## 4. Open questions

Each is stated with why it is hard, not with a proposed answer.

### Q1 — Who owns lifecycle?

When a host framework starts, Agnara must compile and freeze; when it stops,
Agnara must tear down singletons and drain what it owns. Both frameworks
believe they own startup order.

ADR 0029 bridges ASGI lifespan for the case where Agnara is the ASGI
application. Embedded, the host owns lifespan and Agnara is a participant. What
guarantees does Agnara need from a host that has no lifespan concept at all,
such as a WSGI application or a Celery worker?

What happens when the host never signals shutdown — the common case for a
process killed under a supervisor?

### Q2 — Who owns routing?

Embedded, the host owns the URL space entirely and Agnara must not see it.
Side-by-side, both own part of it. Mounting is one answer; explicit per-route
delegation is another; they have different consequences for OpenAPI projection,
because a mounted Agnara sub-application knows its own prefix while a delegated
route does not.

Does an embedded Agnara project OpenAPI at all, or does the host own its own
document and Agnara contribute fragments?

### Q3 — Who owns the dependency container?

The hardest question in the RFC.

Agnara compiles a dependency graph with `SINGLETON` and `INVOCATION` scopes.
FastAPI has `Depends`, Litestar has its own DI, Django has none, Flask has
application and request contexts. Invariant 11 in `docs/INTEROPERABILITY.md`
says Agnara's scope semantics stay Agnara-defined.

So: does a host-provided value enter Agnara as a *provider override*, as a
*context value*, or not at all? If a host's request-scoped session is passed
into an invocation, who closes it — and what happens when the same capability
is invoked twice inside one host request?

Two containers must not both believe they own a connection pool. Stating which
one does is easy; making it impossible to get wrong is not.

### Q4 — The context bridge

An invocation needs correlation identity, a deadline, cancellation and
whatever the host knows. What crosses, in which direction, and what is
deliberately dropped?

A host's request id should become Agnara correlation. A host's raw request
object must not (invariant 5). The line between those two is the bridge, and it
needs to be narrow enough that it cannot be widened accidentally.

### Q5 — The principal bridge

Django auth, DRF permissions, FastAPI security dependencies and a Celery task's
originating user all describe an authenticated subject differently. Agnara has
one `Principal` and evaluates policy against it.

Mapping a host's authenticated user onto a `Principal` is a security boundary,
not a convenience adapter. What happens when the host says "authenticated" and
Agnara's policy needs a scope the host cannot express? What stops an
integration from fabricating a principal with more authority than the host
actually established? I10's confused-deputy analysis applies directly here and
is not yet done.

### Q6 — The error bridge

A capability fails with a canonical `FailureCode`. HTTP maps it to RFC 9457
(ADR 0028). An embedded host has its own error representation and its own
exception middleware.

Does Agnara hand the host a canonical failure and let it map, or offer a
mapping helper per host? The first is the invariant; the second is what
applications will ask for. Where the helper lives decides whether the invariant
survives.

Separately: an exception raised by *host* infrastructure inside a capability —
a SQLAlchemy `IntegrityError`, a Django `DoesNotExist` — has to translate at
the port boundary. Which side of the port owns that translation?

### Q7 — The telemetry bridge

If the host instruments the request and Agnara instruments the invocation,
there must be one span tree, not two. Context propagation across the boundary
has to work in both directions, and it has to work when the host uses
OpenTelemetry, when it uses something else, and when it uses nothing.

ADR 0056 already links transport spans for the case where Agnara owns the
transport. Embedded is the inverse case and is not covered.

### Q8 — Request abstraction

I7 will add cookies, forms, multipart and uploads to `agnara-http`. Embedded,
those already exist in the host and are already parsed.

Does an embedded host re-parse a request into Agnara's binding model, or hand
over already-parsed values? Re-parsing a consumed body is frequently
impossible. Handing over parsed values risks the host's types leaking inward,
which invariant 5 forbids. This question is a prerequisite ordering constraint
on I7, not merely a related concern.

### Q9 — The async and sync boundary

Django and Flask are commonly synchronous; Agnara's execution is async. Calling
async code from a sync host means owning an event loop, and owning an event
loop inside someone else's process is where frameworks acquire their worst
bugs.

Does Agnara provide a synchronous invocation entry point, require the host to
provide the loop, or refuse the sync case and document the constraint? Each
answer has a different blast radius, and the third is a legitimate option.

### Q10 — Adapter discovery

How does an application find the adapter for a port — explicit construction,
entry points, or a registry? Entry points imply a plugin model, which is I13
and deliberately post-1.0. Explicit construction is verbose and safe.

This RFC should probably choose explicit construction and say why, rather than
pull I13 forward.

### Q11 — Multiple applications in one process

Two Agnara applications, or one Agnara application mounted twice, or an Agnara
application inside a host that also mounts a second one. Any design that
resolves the runtime through module-level global state makes this impossible,
and it will not be discovered until someone tries.

What identifies a runtime, and how does an embedded call site name the one it
means?

### Q12 — Nested invocation

A capability invoked from inside a host request that is itself inside another
capability. This is I8's question arriving through a different door: does
policy re-evaluate, does the deadline shrink, does the telemetry nest?

The answer must be the same for an internal call and for a call that re-enters
through a host, or the host path becomes a policy bypass.

### Q13 — Resource ownership

Exactly one side creates a connection pool, an engine, a broker connection, a
thread pool; the same side destroys it. When the host created it and Agnara
uses it, Agnara must not close it. When Agnara created it and the host holds a
reference, the host must not outlive it.

How is that ownership declared, and can it be checked rather than documented?

### Q14 — Shutdown order

Dependent on Q1 and Q13, and worth stating separately because it is where
correct-looking systems corrupt data. If the host closes the database pool
before Agnara drains in-flight invocations, those invocations fail at commit.

What ordering guarantee does Agnara require, what does it offer, and what does
it do when the host provides neither?

### Q15 — Where does the conformance suite live?

`docs/INTEROPERABILITY.md` section 9 defines the scenario. Its home is open:
`agnara-testing` (I12, `BETA`), a repository test tier, or a separate
repository. A suite inside this workspace cannot install FastAPI, Django and
SQLAlchemy without those becoming development dependencies of the workspace,
which is a decision in its own right.

## 5. Constraints on any answer

Non-negotiable. An answer that violates one of these is wrong regardless of how
convenient it is.

1. No answer adds a dependency to `agnara`.
2. No answer requires a host to import a private module.
3. No answer makes the standalone mode worse.
4. No answer makes progressive adoption impossible.
5. No answer is shaped so that only the first framework can implement it.
6. No answer moves the policy evaluation point.
7. No answer lets a host object reach a handler by default.
8. No answer introduces module-level mutable global state to locate a runtime.

Constraint 5 is the one that will be under most pressure, because the first
framework is always the one someone needs working this week.

## 6. Dependencies

| Depends on | Why |
| --- | --- |
| RFC 0006 / I1 | An embedded host invokes an exposure. Until "what a compiled exposure is" is settled, the embedding contract has nothing stable to name. |
| I7 | Q8 constrains how the request surface is designed; designing I7 first and asking Q8 afterwards risks a binding model only Agnara's own ASGI adapter can satisfy. |
| I3 | Q5, Q12 and the Celery analysis all need an execution identity that outlives one invocation. |
| I2 | Streaming across an embedding boundary is a different problem from streaming inside Agnara, and cannot be designed before streaming exists. |
| I8 | Q12 is I8's question re-entering through a host. One answer, not two. |
| I10 | Q5 is a security boundary. The confused-deputy analysis is part of I10. |

I2, I3 and I8 are not blockers for *writing* the answers to Q1 through Q4 and
Q13 through Q14. They are blockers for the parts of the contract that touch
identity, streaming and nesting. Splitting the resulting ADRs along that line
is likely the right shape.

## 7. Non-goals

- Choosing a framework to favour.
- Shipping any integration in `0.1.0a4` or `0.1.0a5` (ADR 0068).
- A universal adapter interface over unlike infrastructure categories.
- A plugin or entry-point discovery model (I13, post-1.0).
- Replacing anything the host already does well: routing, ORM, admin, auth,
  templates, migrations.

## 8. What would make this RFC wrong

Recorded so the next reader can check rather than assume.

- If the embedding contract turns out to need more than the ten steps in
  `docs/INTEROPERABILITY.md` section 7, the capability runtime is doing
  something a host cannot express, and the finding is about the runtime.
- If two frameworks need materially different contracts, the abstraction is
  wrong and one framework's shape has leaked into it.
- If answering these questions requires a kernel dependency, the boundary is in
  the wrong place and the honest outcome is to say so rather than to relax
  invariant 2.

## 9. Decision

None yet. This RFC is the statement of the questions.

When answered, each answer becomes an ADR citing this record, and this file
gains the list.
