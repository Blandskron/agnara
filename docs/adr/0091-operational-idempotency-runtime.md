# ADR 0091 — Operational Idempotency Runtime Boundary

- Status: Proposed
- Date: 2026-09-14
- Tracking: GitHub Issue #400
- Initiative: I3
- Related: ADR 0022, ADR 0025, ADR 0087–0089

## Context

ADR 0089 supplies an atomic, transport-neutral storage port, but deliberately
does not select caller keys, canonical request fingerprints, successful-result
serialization, runtime ordering, or adapter fields.  The current direct,
HTTP, and MCP invocation boundaries do not accept an idempotency selector.
HTTP invokes as an anonymous principal; MCP has no reviewed Agnara
idempotency extension.  Treating a request id, an MCP task field, or free-form
metadata as a selector would violate ADR 0087 and turn untrusted correlation
into execution authority.

The resulting decision must make `Idempotency.YES` operational only when an
explicit, validated selector reaches the runtime.  It must preserve ADR 0025's
policy-before-validation ordering and must not cache failures, cancellations,
or arbitrary Python values.

## Proposed decision

### D1 — An explicit transport-neutral invocation option owns the selector

Add a provisional runtime-owned idempotency option to `ExecutionContext`.
It contains an `IdempotencyScope`, an `IdempotencyStore`, positive lease and
result TTLs, and a caller-supplied value codec that converts only a successful
canonical value to and from bounded opaque bytes.  It is not read from
`Invocation.metadata`, and the runtime verifies that its capability and
principal equal the compiled plan and context before contacting the store.

An absent option leaves the normal path unchanged.  An option for a capability
not declared `Idempotency.YES` is refused; `NO` and `UNKNOWN` never acquire a
reservation or replay a result.  The option does not authenticate a principal
or authorize a capability.

### D2 — The runtime order preserves policy and result semantics

For an opted-in complete-result invocation, the runtime evaluates policy and
confirmation, materializes and validates inputs, then atomically claims the
selector before constructing invocation dependencies or calling the handler.
Thus unauthorized, unconfirmed, and invalid requests create no reservation;
no dependency or handler side effect occurs before a successful claim.

The first claimant executes normally.  A successful, representable result is
completed in the store before it is returned.  A completed duplicate decodes
the stored value and creates a fresh telemetry invocation while retaining the
original logical execution identity.  A fingerprint conflict and an
in-progress reservation are distinct, caller-safe canonical `CONFLICT`
outcomes.  A store or codec failure is a caller-safe `UNAVAILABLE` outcome;
the runtime never executes through it.

Failure and cancellation abandon only the current reservation and are never
cached.  If success cannot be recorded after handler effects occurred, the
runtime fails closed and retains the lease until its configured expiry; no
claim is silently released for an immediate duplicate execution.  Lease expiry
remains a liveness boundary, not proof that an earlier handler stopped.

### D3 — No transport selector is added by this decision

This decision adds no HTTP header, MCP request field, task-resumption field,
or default/global store.  An adapter can use the runtime option only after a
separate accepted adapter decision defines its authenticated principal,
selector input, canonical fingerprint, codec, error projection, and
conformance evidence.  In particular, the anonymous HTTP baseline cannot
provide a principal-scoped public selector, and MCP has no reviewed standard
field for one.

## Threat and concurrency analysis

Keys and fingerprints stay untrusted.  Capability and principal matching at
the runtime boundary prevents an application-provided scope from selecting a
different namespace.  Policies and confirmation are always evaluated before
lookup/reuse, so a stored result never bypasses current authorization or
approval.  The store's atomic claim decides concurrent matching calls; the
runtime does not implement check-then-act state.

The result codec is a trusted application/adapter boundary.  It must not log
or disclose opaque stored bytes.  A process-local store remains unsuitable for
multi-process deployments.  No lease duration can prove a process stopped;
deployments needing stronger guarantees require a durable store and separately
reviewed operational bounds.

## Alternatives

### Add `Idempotency-Key` to HTTP now

Rejected pending an authenticated HTTP principal contract.  Scoping every
public caller to `anonymous` permits one client who learns a key and matching
payload to retrieve another client's completed result.

### Reuse HTTP/MCP request identifiers or MCP task state

Rejected because those values are correlation or protocol-resumption material,
not authenticated idempotency selectors.

### Make the in-memory store a global default

Rejected because it makes process-local state invisible, loses records on
restart, and cannot protect multi-worker deployments.

### Cache failures or retry idempotent handlers automatically

Rejected because neither permission nor retry policy follows from an
idempotency declaration.

## Required evidence before acceptance

- Direct normal, conflict, in-progress, failure, cancellation, storage-failure
  and deterministic concurrent-race tests prove a handler's side effect runs
  once.
- Tests prove cross-capability and cross-principal selector misuse is refused
  at the runtime boundary and policy/confirmation are re-evaluated on reuse.
- The public API manifest/reference and threat model describe the exact
  provisional runtime surface and remaining untrusted boundaries.
- Any adapter projection has its own accepted selector/principal/fingerprint
  decision and conformance evidence; it is not implied by this ADR.
