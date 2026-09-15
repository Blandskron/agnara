# ADR 0093 — Nested Capability Invocation Contract

- Status: Accepted
- Date: 2026-09-15
- Tracking: GitHub Issue #410
- Initiative: I8
- Related: ADR 0022, ADR 0023, ADR 0024, ADR 0025, ADR 0084, ADR 0087–0091; RFC 0005, RFC 0008

## Context

A capability handler can call ordinary Python functions, but that is not a
capability invocation: it skips the target's compiled plan, policies,
confirmation, validation, dependency ownership, canonical result semantics,
deadline and telemetry. Letting a handler obtain another handler directly
would therefore create a confused-deputy path in which possessing a Python
reference is mistaken for authority to execute a capability.

The kernel already has frozen compiled plans, per-execution contexts, an
opaque execution identity, per-attempt telemetry identity, direct complete
result idempotency, and separately owned streams. RFC 0005 also requires an
explicit nested API before delegation can reach a new target. What was missing
was the contract joining those boundaries without creating a second unrelated
application/runtime or importing a host framework into the kernel.

This record decides that contract only. It adds no public symbol, runtime
implementation, adapter selector, durable workflow, transaction abstraction,
or cross-application transport.

## Decision

### D1 — A nested call targets a compiled plan in the same compiled application

The future composition entry point belongs to the compiled application/runtime
boundary, not to a handler, transport adapter, or global registry. It accepts
an explicit target capability identity and arguments, resolves that identity
from the caller's already-frozen compiled registry, and invokes the target's
compiled `ExecutionPlan`. It must reject an absent target and a target outside
that compiled application before target dependencies or effects run.

It creates a child execution; it does not construct another `Agnara`, compile
another registry, re-enter a transport, or call the target Python handler.
There is no ambient "current runtime" lookup. A handler receives only an
explicit, invocation-scoped composition capability supplied by the plan; it
cannot turn an arbitrary callable or application object into a privileged
capability invoker.

Cross-application composition is deliberately refused in this increment.
Passing a foreign plan, registry, app object, host request, ORM session, or
transaction object is not a substitute for a future inter-application/host
contract. RFC 0008 owns that later boundary.

### D2 — A child receives a fresh context, with narrowly derived values

Every child receives a fresh `ExecutionContext`, a fresh generated
`execution_id`, and a fresh telemetry `invocation_id` for each actual attempt.
The parent and child identities are never aliases. Telemetry records a
redacted causal parent/child link and may share a trace parent through the
telemetry bridge, but neither linkage is authority or an idempotency selector.
Caller-supplied tracking/correlation remains untrusted correlation only; the
child may copy a bounded value for correlation but may not promote it to an
execution or invocation identifier.

The child derives its deadline as the earlier of the parent absolute deadline
and an explicit child limit accepted by the future composition API. A child
never extends a deadline or invents a new clock. Child work is owned structured
concurrency: cancellation of the parent task cancels awaited child work, and a
child cancellation propagates as cancellation rather than becoming a canonical
failure. A parent may map a child's ordinary canonical failure deliberately in
its own business result, but the composition boundary itself returns the
child's `CanonicalResult` unchanged and does not hide an authorization,
confirmation, timeout, or unavailable failure as success.

`principal` remains the authenticated actor and is copied only as an immutable
identity input for target policy evaluation. A verified RFC 0005 subject and
delegation may reach a child only through the explicit, target-bound attenuation
and verification path specified by that RFC; the child does not inherit raw
evidence, a mutable context, or a bypass. In the initial runtime increment,
where that delegated path is not implemented, nested calls use direct actor
authority only. Scopes are recomputed by the target policy and are never
unioned with parent scopes. Parent authorization does not authorize a child.

Confirmation evidence never propagates implicitly. The target independently
evaluates its confirmation requirement; evidence is accepted only when a
future verifier can bind it to the child actor, subject/delegation fingerprint
when present, target capability, normalized child input, expiry and replay
constraints. A parent confirmation cannot approve a different child effect.

### D3 — Invocation-scoped dependencies and idempotency are isolated

The child resolves its own compiled dependency graph in a new invocation
scope. It cannot read the parent's `ExecutionContext.state`, parent
invocation-scoped dependency instances, cleanup stack, effectful provider
values, host request/session objects, or external transaction handles.
Application/singleton dependencies may be shared only through the existing
compiled container ownership rules; the composition layer creates and closes
only the child scope it owns. No framework transaction, session, request or
ambient context enters normal core handlers through composition.

An idempotency selector is not inherited. A child may use idempotency only if
it is `Idempotency.YES` and a future explicit child option supplies a new
validated `IdempotencyScope` bound to the child capability, authenticated
principal and child request fingerprint, as required by ADR 0089 and ADR 0091.
The parent key, execution id, codec, reservation and completed result are
never reused as a child namespace. Composition never retries a child merely
because either capability is declared idempotent.

### D4 — Streams, recursion and failure ownership stay explicit

The first nested composition API has complete-result semantics only. It must
refuse a streaming child rather than return its producer through `Success` or
borrow its iterator/cleanup. A future stream-composition decision must define
one owner for iteration, backpressure, partial failure and cancellation and
preserve ADR 0084/0086; it cannot be added as a convenience overload.

The future runtime maintains an immutable composition ancestry of capability
identities in the child context. It rejects an identity already in that chain
and enforces a finite, compiled application composition-depth limit before
target work. The initial public spelling and default limit are deferred to the
runtime/API review; the limit must be positive, bounded, deterministic, and
cannot be raised by handler arguments or caller metadata. This protects both
direct and indirect cycles without a process-global mutable registry.

The target runs the normal compiled sequence independently: policy and
confirmation; input materialization/validation; idempotency claim where
explicitly configured; child dependency resolution; handler; output
validation; child lifecycle telemetry. A target denial or confirmation request
therefore happens before child dependencies/effects. This preserves the
security-sensitive order in ADR 0025 and ADR 0091.

## Required acceptance evidence for the runtime increment

The implementation issue must add deterministic tests for these examples:

| Scenario | Required observation |
| --- | --- |
| Authorized parent and child | Both compiled plans run; child has a distinct execution/invocation identity and a causal telemetry link. |
| Child policy denial | Parent may be authorized, but child handler and effectful dependencies do not run; its canonical denial is returned unchanged. |
| Child confirmation requirement | Parent confirmation does not satisfy the child; the child requests/validates target-bound evidence before effects. |
| Deadline exhaustion | Child gets no later deadline; timeout prevents child effects when time is exhausted. |
| Parent cancellation | Awaited child work and owned dependency cleanup are cancelled with the parent; no cancellation is converted to success/failure. |
| Direct or indirect recursion | Repeated capability identity and excessive depth are refused before target dependencies/effects. |
| Foreign application/plan | Cross-app target is refused; no second runtime, transport re-entry, or host object is created. |
| Idempotency isolation | A parent selector/key cannot replay, reserve, or retry a child; an explicit valid child scope remains independent. |

The threat analysis must prove that a handler cannot use composition as ambient
authority, cannot amplify scopes or swap actor/subject, cannot replay parent
confirmation for a child, cannot extend a deadline, and cannot smuggle host
transaction/request state across invocation scope. It must also test
concurrent independent parent executions so ancestry and child state do not
leak across tasks.

## Consequences

- Capability-to-capability work has one kernel path and one policy boundary;
  direct Python calls remain ordinary application code, not an authorization
  bypass blessed by the framework.
- The decision is transport- and framework-neutral. HTTP, MCP, streams,
  embedded hosts and any future adapter must preserve it rather than redefine
  nested semantics.
- `docs/MATURITY.md` may state `DESIGNED`, but no nested invocation behavior
  is implemented or supported until the named runtime evidence exists.

## Alternatives rejected

### Pass the parent `ExecutionContext` to the target

Rejected. It aliases execution identity, state, invocation dependencies and
confirmation, making policy bypass and resource-ownership leaks easy.

### Call a target handler directly

Rejected. It bypasses compiled validation, policies, confirmation, telemetry,
deadlines, output validation and dependency cleanup.

### Inherit parent authorization, idempotency or confirmation

Rejected. Each makes the parent a confused deputy and permits a broader or
different effect than the evidence authorized.

### Re-enter a transport or construct a second runtime

Rejected. It duplicates application state, imports adapter semantics into the
kernel, and creates an alternate policy/lifecycle path.

### Allow streaming children now

Rejected. No component would yet own the producer lifecycle, backpressure and
post-output failure semantics.

## Deferred work

- The public composition API spelling, the compiled depth-limit configuration,
  runtime implementation and conformance suite.
- Explicit delegated nested authority after RFC 0005 has an implemented
  verifier/attenuation boundary.
- Stream composition and cross-application/embedded-host invocation, which
  require their own decision records and RFC 0008 conformance evidence.
