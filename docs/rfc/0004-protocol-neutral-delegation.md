# RFC 0004 — Protocol-neutral delegation

- Status: Draft
- Date: 2026-09-02
- Tracking: GitHub Issue #101
- Target: Policy engine after E5.6

## Summary

Agnara models delegation as verified, explicitly attenuated authority carried
alongside the authenticated actor. The actor never becomes indistinguishable
from the represented subject, and no token, protocol claim or invocation
metadata is trusted directly by core.

The first model supports delegation only. Impersonation is deferred because it
intentionally hides the actor from ordinary authorization decisions and would
weaken Agnara's audit and confirmation guarantees.

## Motivation

A capability may be invoked by a service, agent or worker acting for another
principal. Treating the current caller as the represented principal loses who
performed the action. Copying the represented principal's scopes to the caller
allows privilege amplification. Passing an OAuth/JWT/MCP object through
`Invocation.metadata` would make a transport or credential format the semantic
source of truth.

Agnara needs a common security meaning that can be supplied by OAuth token
exchange, workload identity, application grants or another authority without
requiring any of them in `agnara-core`.

## Terminology

- **actor**: the currently authenticated entity performing the invocation.
  `ExecutionContext.principal` continues to identify this entity.
- **subject**: the principal on whose behalf the actor is operating.
- **grantor**: the principal that authorizes one delegation hop.
- **grantee**: the principal receiving authority in that hop.
- **delegation hop**: one verified grant from a grantor to a grantee, including
  its authority constraints.
- **delegation chain**: an ordered sequence from the subject through any
  intermediate actors to the current actor.
- **authority envelope**: the maximum authority that may survive at one point
  in the chain.
- **effective authority**: the intersection of every verified envelope and
  restriction applicable to the current invocation.
- **delegation evidence**: opaque input supplied to a configured verifier. It
  is not authority until verification succeeds.

Identity equality and canonicalization belong to the configured identity and
delegation authority. Core does not compare display names or raw token claims.

## Goals

- preserve both the represented subject and the actual actor;
- prevent authority amplification across every hop;
- make capability, audience, time and input restrictions enforceable;
- support bounded multi-hop delegation without protocol coupling;
- bind confirmation and audit events to the verified delegation;
- remain safe under cancellation, deadlines and free-threaded execution.

## Non-goals

- defining an OAuth flow, JWT claim set, credential or signature format;
- minting, refreshing, revoking or storing delegation credentials;
- supporting transparent impersonation in the first model;
- treating delegation as proof of authentication or confirmation;
- exposing a delegation chain automatically through discovery;
- defining cross-domain trust establishment.

## Decision

### Actor and subject remain distinct

The authenticated actor always remains `ExecutionContext.principal`. A
verified delegation context separately identifies the subject and ordered
chain. Handlers, policies and telemetry can therefore answer both:

```text
who performed this invocation?
for whom was it performed?
```

Without delegation, the actor acts directly for itself. Core does not create a
synthetic one-hop chain and existing direct invocation behavior remains
unchanged.

The first implementation must not replace the actor with the subject or offer
an `impersonate=True` shortcut. A future impersonation design requires a
separate security RFC and must preserve an audit-visible original actor even
if a protocol presents another subject to a downstream system.

### Evidence is verified through a port

Core will define an asynchronous delegation-verifier protocol. Concrete names
and field spelling remain an API review concern, but the semantic boundary is:

```text
opaque delegation evidence
+ authenticated actor
+ target capability
+ invocation input
+ configured audience
        ↓
delegation verifier
        ↓
verified normalized chain | invalid
```

The verifier owns:

- credential syntax, signature and issuer validation;
- trust-domain and identity canonicalization;
- revocation, expiry and not-before validation against a trusted clock;
- proof-of-possession or sender constraints where required;
- replay and one-time-use rules;
- application-specific restriction evaluation;
- normalization into immutable protocol-neutral values.

Core never interprets a JWT, OAuth token, cookie, header, MCP field, API key or
arbitrary metadata entry as delegation.

An unexpected verifier exception fails closed and is redacted at the canonical
boundary. Cancellation and invocation deadlines propagate while verification
runs. Core creates no orphan verification task.

### Chain structure is explicit and bounded

A normalized chain is ordered from the subject toward the current actor:

```text
subject/grantor → intermediate grantee/grantor → current actor
```

For every adjacent hop:

- the previous grantee must equal the next grantor;
- the final grantee must equal the authenticated actor;
- every identity may occur at most once;
- every hop must be authentic and currently valid;
- onward delegation must be explicitly permitted by the prior hop;
- the configured maximum chain depth must not be exceeded.

Missing links, reordered links, repeated identities, ambiguous identity
comparison and excessive depth are invalid delegation. The maximum depth is
application configuration with a finite enforced bound; evidence cannot raise
it.

### Authority only attenuates

The initial authority envelope comes from a trusted authorization boundary for
the subject, not from caller metadata. Each hop produces an envelope that must
be no broader than the incoming envelope.

The first implementation supports monotonic constraints with deterministic
intersection:

- granted scopes;
- exact target audiences/resources;
- exact capability identities;
- validity interval and expiry;
- permission to delegate onward;
- remaining maximum delegation depth;
- an optional verifier-owned binding to the normalized invocation input.

For set constraints, the outgoing set must be a subset of the incoming set.
For time and depth constraints, the outgoing bound must be equal or narrower.
An omitted restriction inherits the previous restriction; omission never
widens it. Wildcards, patterns and negative permissions are deferred until an
RFC defines deterministic intersection semantics.

The effective authority is the intersection that survives all hops. A valid
chain with insufficient effective authority is denied. It does not fall back
to the subject's original scopes or the actor's unrelated direct grants.

Application-specific constraints may be evaluated by the verifier or an
explicit policy. Core must not claim to compare opaque restrictions it cannot
understand.

### Delegation is invocation-scoped

Verified delegation is immutable and belongs to one `ExecutionContext`. It is
not stored in global mutable state and is not inherited implicitly by another
invocation or background task.

A nested capability call receives delegation only through an explicit API that
re-evaluates the target capability and attenuation rules. Passing the same
context object or copying invocation metadata must not silently authorize a
new target.

Caches used by a verifier are owned by that implementation and require
documented synchronization, expiry and revocation behavior. Core does not rely
on accidental GIL serialization.

### Policy ordering

The intended security order is:

```text
authenticate actor
→ validate/normalize target input required by policy
→ verify delegation evidence and derive effective authority
→ evaluate scope and application policies against effective authority
→ verify confirmation bound to actor + subject + delegation + target + input
→ construct effectful invocation dependencies
→ invoke handler
```

The later implementation change must fix the exact position of input
validation and dependency construction with tests. No handler or effectful
business dependency may run before required delegation, policy and
confirmation gates succeed.

Policies receive a safe verified view, never raw evidence. A scope policy uses
the effective delegated scopes when a verified delegation is present and the
actor's direct scopes otherwise. It must not union both sources implicitly.
An explicit application policy may independently require the actor's own
authority in addition to the delegated authority when the use case demands it.

### Confirmation binding

Confirmation evidence for a delegated invocation must bind at least:

- authenticated actor identity;
- represented subject identity;
- a stable verifier-produced fingerprint of the complete effective delegation;
- capability identity;
- normalized input or its application-defined digest;
- expiry and replay constraints required by the approval authority.

Changing, shortening or extending the chain creates a different binding.
Confirmation for direct authority cannot be replayed under delegated authority,
or vice versa. Raw delegation evidence and secrets are never embedded in an
interaction request.

### Failure semantics

- no evidence: direct invocation unless an explicit policy requires
  delegation;
- required delegation with no evidence: protocol-neutral forbidden outcome;
- supplied invalid, expired, revoked, cyclic or mismatched evidence: forbidden;
- valid but insufficient effective authority: forbidden;
- verifier infrastructure or invalid verifier output: redacted internal
  failure;
- deadline expiry: timeout;
- external cancellation: propagated cancellation.

When evidence is supplied but invalid, runtime must not silently retry as a
direct invocation. Public failures do not reveal which hop, issuer, scope or
constraint failed. Detailed diagnostics belong only in access-controlled
operator telemetry.

Delegation acquisition is not confirmation. The first model does not emit an
interaction-required outcome merely because delegation is absent.

### Telemetry, audit and discovery

Security audit records may include, subject to application policy:

- actor and subject stable identifiers;
- chain depth;
- verifier/authority identifier;
- non-secret delegation fingerprint;
- target capability;
- allow/deny outcome and a private reason code.

They must not include raw credentials, signatures, confirmation evidence,
unfiltered claims or sensitive authorization details by default. Telemetry
hooks receive a redacted descriptor, not the verifier input.

Discovery may state that a capability accepts or requires delegation and may
publish explicitly safe constraint vocabulary. It must not expose live chains,
principal identifiers, internal trust topology, verifier configuration or
policy diagnostics.

## Security invariants

1. Delegation never authenticates the current actor by itself.
2. Delegation never manufactures authority absent from the trusted initial
   envelope.
3. Each hop is equal to or narrower than every previous hop.
4. Onward delegation is denied unless explicitly granted.
5. The current actor and represented subject remain distinguishable.
6. Raw evidence and invocation metadata are never authorization.
7. A supplied invalid chain never falls back to direct authority.
8. Confirmation is bound to the effective delegation, not merely the subject.
9. Chain validation completes before handler effects.
10. Failure output does not become a delegation-validation oracle.

## Considered alternatives

### Replace the actor with the represented subject

Rejected. This is impersonation, loses accountability and allows policies to
mistake the caller for the authority owner.

### Copy or union scopes across principals

Rejected. Union permits privilege amplification. Delegated authority is an
intersection of trusted, monotonically narrowing envelopes.

### Store a token or claims dictionary on `Principal`

Rejected. It couples core to a credential format, encourages unverified claim
use and risks leaking secrets through representation, telemetry or discovery.

### Trust a delegation chain supplied in invocation metadata

Rejected. A caller can forge or reorder it, bypass depth limits and substitute
identities.

### Accept arbitrary policy predicates in each hop

Deferred. General predicates do not have a safe, deterministic attenuation or
intersection rule. Applications can enforce additional verified restrictions
through explicit policies.

### Allow unlimited transitive delegation

Rejected. Every hop expands the attack and audit surface. Onward delegation
and a finite depth bound are explicit.

## Standards relationship

These are informative mappings, not dependencies:

- [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693) distinguishes delegation
  from impersonation, preserves subject and actor, and defines an `act` chain
  for OAuth token exchange. An adapter may verify such tokens and normalize
  them into Agnara's model.
- [RFC 8707](https://www.rfc-editor.org/rfc/rfc8707) demonstrates audience/
  resource restriction for OAuth authority. Agnara keeps the restriction
  semantic but not the OAuth parameter.
- [RFC 9396](https://www.rfc-editor.org/rfc/rfc9396) provides structured rich
  authorization details and highlights integrity and privacy requirements.
- [RFC 9635](https://www.rfc-editor.org/rfc/rfc9635) describes privilege
  delegation in GNAP. A future adapter may map its grants without making GNAP
  a core dependency.
- The IETF OAuth identity-chaining draft is work in progress and is considered
  research only. Agnara must not claim conformance to an unstable draft.

## Implementation sequence

1. Review public names and add immutable opaque evidence, normalized hop,
   authority-envelope and verified-delegation contracts.
2. Define the asynchronous verifier port and structural validation boundary.
3. Add delegation to `ExecutionContext` without changing `Principal` identity.
4. Compile delegation requirements and maximum depth into execution plans.
5. Derive effective authority before scope, application and confirmation
   policies.
6. Bind confirmation verification to the effective delegation fingerprint.
7. Add protocol-neutral tests for attenuation, actor/subject separation,
   cycles, depth, expiry, audience, target/input binding, invalid-evidence
   downgrade prevention, cancellation, deadlines, redaction and zero effects.
8. Add independent adapter mappings and conformance tests as transports are
   implemented.

E5.6 is complete when this RFC is accepted. Runtime delegation remains a
separate Issue and must not be inferred from documentation alone.

## Open questions for implementation review

- Exact public type and constructor names.
- Whether the initial subject authority is always verifier-produced or can use
  another explicitly trusted authorization provider.
- The configured audience identifier exposed by the application composition
  root.
- Whether safe delegation descriptors become part of public introspection in
  the first runtime increment.

## Revisit when

- a transport requires semantics that cannot be normalized without loss;
- cross-domain trust establishment becomes product scope;
- application constraints need a standard deterministic algebra;
- impersonation is proposed with a concrete compatibility requirement.
