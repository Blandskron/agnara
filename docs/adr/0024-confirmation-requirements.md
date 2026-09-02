# ADR 0024 — Protocol-neutral confirmation requirements

- Status: Proposed
- Date: 2026-09-02
- Tracking: GitHub Issue #94

## Context

Capabilities already declare `Confirmation.NEVER`, `Confirmation.POLICY`, or
`Confirmation.REQUIRED`. That declaration is metadata, not proof that a human
approved an invocation. Core also reserves the canonical
`FailureCode.INTERACTION_REQUIRED`, but policy results currently distinguish
only success from failure and the runtime does not yet orchestrate policies.

Confirmation crosses security boundaries. A transport can collect a click,
an MCP elicitation response, or an approval-service reference, but none of
those protocol values may become the semantic source of truth. A raw
`confirmed=true` supplied by a caller would be forgeable, and an approval for
one principal, capability, or payload must not authorize another invocation.

The golden `ctx.require_confirmation(...)` example is explicitly provisional.
Running arbitrary handler code before confirmation can allow effects to occur
before execution pauses, so that syntax cannot be accepted without a separate
execution model.

## Decision

### Declaration, interaction, and evidence are separate

Agnara treats these as three different concepts:

1. **Confirmation declaration** describes a capability's intended behavior.
2. **Interaction request** tells a caller that verified confirmation is
   required before execution can continue.
3. **Confirmation evidence** is an opaque reference evaluated by an explicit
   verifier. It is never trusted merely because a transport supplied it.

The declaration has these semantics:

- `NEVER`: Agnara adds no confirmation requirement for this declaration. It
  does not bypass another authorization or application policy.
- `POLICY`: an explicit application policy decides whether the invocation may
  proceed, must be denied, or requires confirmation.
- `REQUIRED`: the compiled policy stage requires valid confirmation evidence
  for every invocation before the handler may run.

Changing metadata cannot grant authority. In particular, changing
`REQUIRED` to `NEVER` only removes that declaration's confirmation gate; it
does not manufacture scopes, identity, delegation, or another permission.

### Policy evaluation gains an interaction-required outcome

The policy domain will add a third result alongside success and denial. The
semantic shape is an immutable interaction request with:

- a stable kind identifying confirmation;
- a caller-safe title and message;
- the target capability identity;
- immutable, explicitly publishable hints only.

It contains no transport object, callback, secret, raw approval token, policy
implementation detail, or executable value. The exact public class names and
field spelling remain an implementation/API review concern, but the tri-state
meaning is fixed:

```text
allow | deny | interaction required
```

`invoke_result(...)` will map the third state to
`FailureCode.INTERACTION_REQUIRED`. A direct `invoke(...)` call will use a
typed protocol-neutral exception so ordinary Python exception semantics are
preserved, following ADR 0022.

### Evidence is verified through a boundary

Core will define a verifier port; applications or adapters provide its
implementation. Core does not define approval credentials, signing formats,
databases, user interfaces, or cryptography.

A verifier must establish that evidence is:

- authentic according to the configured approval authority;
- bound to the exact capability identity;
- bound to the authenticated principal, including relevant delegation;
- bound to the invocation input or to an application-defined canonical digest
  of that input;
- unexpired and, when required by the application, single-use or replay-safe.

The verifier owns canonicalization and storage rules. Core passes the
transport-neutral invocation and policy target; it never treats an arbitrary
metadata key, header, cookie, query value, MCP field, or boolean as proof.

No evidence means the policy returns interaction required. Evidence that is
present but invalid, expired, replayed, or mismatched is a denial rather than
a fresh interaction request. This distinction avoids turning forged evidence
into an approval oracle.

### Confirmation precedes handler effects

Required confirmation is evaluated after identity and input are available but
before the capability handler runs. The handler cannot perform business side
effects before confirmation succeeds. Providers used by authentication or
confirmation verification must have explicit lifecycle ownership; the final
ordering relative to validation and dependency construction is fixed in the
runtime-policy integration change with security-sensitive tests.

Cancellation and invocation deadlines continue to propagate while a verifier
runs. Core does not create an orphan task that waits for a human. Interaction
required terminates the current invocation; a later invocation supplies newly
verified evidence and is evaluated from the beginning.

### Dynamic in-handler confirmation is deferred

The provisional `ctx.require_confirmation(...)` API is not part of the first
implementation. Dynamic decisions should initially be expressed as a
pre-handler policy that can inspect validated input. Supporting a resumable
handler later requires a dedicated RFC covering checkpointing, duplicated
effects, cancellation, replay, and task ownership.

## Security and privacy guardrails

- confirmation metadata is never authorization by itself;
- evidence and verifier diagnostics are not included in public failures,
  discovery documents, telemetry events, or logs by default;
- caller-safe interaction text cannot contain secrets or internal policy
  structure;
- transports map canonical outcomes and do not independently decide whether
  confirmation succeeded;
- confirmation does not replace scopes, authentication, delegation, tenant
  isolation, or other policy checks;
- a verifier failure is fail-closed and unexpected verifier exceptions are
  redacted at the canonical boundary.

## Considered alternatives

### Trust a boolean or string in invocation metadata

Rejected because callers can forge it and because it cannot prove binding to
the principal, capability, or payload.

### Put confirmation UI or protocol objects in core

Rejected because HTTP, MCP, A2A, CLI, and task systems collect interaction in
different ways. Those are adapter responsibilities.

### Pause inside the capability handler

Deferred because arbitrary code may already have produced effects, and safely
resuming it requires a task/checkpoint model that Agnara does not yet define.

### Treat missing and invalid evidence identically

Rejected because an absent approval is a normal interaction requirement,
while invalid supplied evidence is a security failure and must not become an
oracle that repeatedly solicits approval.

## Consequences

Positive:

- every transport receives the same confirmation semantics;
- approval evidence remains replaceable and application-controlled;
- handlers do not execute before required confirmation;
- replay and confused-deputy risks are explicit acceptance criteria;
- canonical interaction-required mapping fits the taxonomy in ADR 0022.

Negative:

- E5.5 requires policy-result and runtime integration work before it is done;
- approval systems must implement a verifier and binding rules;
- the initial model terminates and restarts invocations instead of suspending
  handlers;
- dynamic in-handler confirmation remains unsupported.

## Implementation sequence

1. Add immutable interaction-request and policy-result types.
2. Define the confirmation-evidence/verifier port and fail-closed policy.
3. Compile `REQUIRED` declarations and explicit `POLICY` evaluators into the
   execution plan.
4. Evaluate policies before handler execution and map canonical/direct-call
   outcomes according to ADR 0022.
5. Add protocol-neutral tests for binding, missing versus invalid evidence,
   denial ordering, cancellation, deadlines, redaction, and no handler effects.
6. Map the canonical outcome independently in each transport adapter.

The protocol-neutral stages 1–5 were implemented and verified by GitHub Issue
#96. Transport adapters still map the canonical outcome independently as they
are implemented; they do not redefine confirmation semantics.

## Revisit when

- delegation semantics in E5.6 define additional evidence binding;
- long-running task/checkpoint semantics can support resumable interaction;
- a concrete protocol exposes a requirement that cannot be represented by the
  canonical interaction request without leaking transport semantics.
