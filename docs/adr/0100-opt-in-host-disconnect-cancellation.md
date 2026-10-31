# ADR 0100 — Opt-in host cancellation for disconnected A2A requests

- Status: Proposed
- Date: 2026-10-30
- Tracking: GitHub Issue #709
- Related: ADR 0024, ADR 0094, ADR 0098 D10, ADR 0099, RFC 0010

## Context

The A2A-04b2 [loopback tests](../../tests/a2a/test_a2a_network.py) show that the
Uvicorn 0.52.4/h11 host does not cancel an active request task when its peer
disconnects. The kernel deadline still cancels a cooperative waiting handler
and releases invocation resources. Closing a socket is therefore different
from cancelling its application task, as clarified in ADR 0098 D10.

Some hosts may want to stop work when its caller leaves. That is an application
policy with consequences for effects and cleanup, not permission inferred
from a message, capability risk or client-supplied flag. The public adapter
does not currently offer this policy, and no new builder option or core
contract is required to investigate it.

## Proposed decision

Recommend an **explicit host-owned policy around a dedicated A2A ASGI
surface**, while retaining the current deadline-owned adapter behavior by
default. The initial proposal/prototype was reviewed in PR #710; follow-up
Issue #711 provides a copyable application-owned recipe and exact-source
installed-wheel/host evidence. This is not a supported framework wrapper or
public API, and it does not change this record's `Proposed` status.

### D1 — Composition and authority

The host chooses the policy at composition, after installing its trusted
authentication result in the scope. A request cannot enable or disable it.
The policy reads no credentials, selects no principal, evaluates no capability
policy and classifies no business failure. The adapter and kernel retain all
their existing authentication, materialization, authorization, DI and output
contracts. Discovery metadata never grants authority.

The application recipe wraps only HTTP POST calls to the dedicated surface. GET/card
and lifespan traffic pass through with the original callables. It does not
claim support for other middleware stacks, generic HTTP streaming, WebSockets,
MCP, A2A tasks or other hosts and bindings.

### D2 — One lazy receive owner with bounded buffering

A request owns one application task and one receive-pump task in a
`TaskGroup`. Only the pump calls the underlying ASGI `receive`. It starts
reading only after the application first requests input. A refusal before
that point can return without reading any body; starting an eager monitor
before authentication would change that boundary and is rejected.

A capacity permit and a one-slot FIFO allow at most one queued or currently
being received event, in addition to whatever event the application already
owns. The pump cannot read the next event while the slot is full. The original
event object, bytes and `more_body` marker pass through unchanged and in order.
There is no second JSON parser or whole-body copy. Existing host chunk limits
and the adapter's total-body limit remain necessary; an event-count bound is
not a new byte bound. All mutable state belongs to one request/event loop.

If an application stops consuming an incomplete body while the slot is full,
the pump deliberately does not drain more data merely to find a disconnect.
Detection can then wait for the next application read. The target A2A gate
consumes the body before entering a capability; a generic application that
starts long work with unread input is outside this evidence.

### D3 — Cancellation and joining

When the receive owner observes `http.disconnect` before a terminal response
has completed, it cancels the pending application task and joins its cleanup.
It stops and joins the pump when the application ends. Success, application
errors, receive/send errors and caller cancellation all leave through the same
structured owner; no detached watcher or global connection registry is used.

The outer host may suppress only the `CancelledError` it deliberately caused
for a disconnected peer. Cancellation of the outer request owner still
propagates, including when it races with disconnect-triggered cleanup.
Non-cancellation exceptions propagate through `TaskGroup`; the recipe does
not serialize their diagnostics or turn them into a canonical business error.
An infrastructure error-response/logging policy remains the host's concern.

### D4 — Completed responses and races

Completion means the final `http.response.body` event with `more_body=False`
has been accepted by the downstream `send`. Headers alone do not complete a
response. A completed response or an already finished application wins over
a later disconnect, and its remaining cooperative cleanup is joined without
adding a disconnect cancellation.

This matters because Uvicorn can return `http.disconnect` from `receive`
after a response completes, even when this is not evidence of a new peer
failure. The wrapper must not interrupt successful-response cleanup on that
signal. A transport `send` error is preserved as an error, not fabricated as a
capability outcome. Completion is an observed ASGI boundary, not proof that a
remote client consumed or persisted the response.

### D5 — Limits and effects

Cancellation is cooperative. The policy cannot interrupt blocking synchronous
code or force a handler/provider that suppresses cancellation to terminate.
The kernel deadline and host shutdown ownership remain independent safeguards;
the recipe adds no replacement timeout. Body size bounds do not establish
a read-time bound for a slow peer; hosts still own appropriate admission and
read/shutdown timeouts.

Cancelling work does not roll back effects already performed, establish
delivery, provide durable execution or make retries safe. Client message IDs
remain untrusted correlation values, not idempotency keys (ADR 0098 D9).
Applications must decide whether disconnect cancellation fits their operation
and persistence contracts. The policy grants no authorization, confirmation or
transactional guarantee.

## Evidence and boundaries

The [original prototype checkpoint](https://github.com/Blandskron/agnara/blob/46307ea2635b6c7799ec92d1afab87e4308a4205/experiments/a2a/disconnect_policy.py)
was isolated research under #709. The implementation now lives once, in the
application-owned [recipe source](../../examples/a2a_disconnect.py), following
review of PR #710 and the maintainer's continuation in #711. No shipped package
imports it; there is no public manifest/builder/dependency/default change.

[Recipe tests](../../tests/a2a/test_a2a_disconnect_recipe.py) retain no-read
refusal, pass-through traffic, event identity/order, bounded prefetch with a
single reader, application/receive/send errors, outer cancellation during
peer-triggered cleanup, completed-response cleanup and joined tasks.

The real Uvicorn/h11 tests use the recipe explicitly for mid-body/post-entry
socket closes with a 30-second kernel deadline beyond the outer fixture/test
bounds. Passing requires peer-triggered cleanup, not deadline expiry. The
unwrapped host tests retain the original deadline-owned behavior.

The [installed-source consumer](../../tests/reference_apps/a2a_disconnect_guide.py)
copies the exact recipe, demonstration and pinned host fixture outside the
checkout and runs under Python `-I` against installed candidate wheels. It
checks ordinary outcomes/redaction/cleanup, real socket disconnects, 401 without
a body read, invalid input, policy denial, a body limit before effects, recovery
and graceful draining before container close. CI on its final commit owns the
cross-platform evidence. This record does not certify a platform or deployment.

## Alternatives

| Option | Benefit | Cost / disposition |
| --- | --- | --- |
| Deadline-only adapter behavior | Smallest ownership model; preserves current callers and semantics. | Work can continue until its cooperative deadline after a peer leaves. Retained as the default. |
| Explicit host-owned policy | Host controls receive ownership, deployment and effects policy without changing Agnara's public API. | Two owned tasks per monitored request and coordination with other receive consumers. Recommended for a separately reviewed opt-in pattern, backed by the reviewed recipe and its bounded evidence. |
| Adapter/builder flag | A single adapter could govern and test a reusable option. | Adds a public contract and assumptions about upstream receive consumers, middleware and host cancellation. Deferred until host evidence and an API need justify it. |
| Core disconnect handling | Could appear uniform across transports. | A socket/ASGI event is protocol-specific, while core already propagates task cancellation. Rejected: no protocol dependency or new request type belongs in the kernel. |

No task/transport facade, core cancellation token or automatic classification
from capability metadata is introduced by selecting the host recipe.

## Implementation boundary and remaining decisions

Issue #711 implements the reviewed application-owned scope: a copyable module,
explicit composition hook, unchanged default, retained ownership/race tests and
exact installed-wheel/host evidence. It does not import the historical
experiment or add a package export. A new public export or builder option would
require its own API proposal.

Any formal status change for this record, broader host/support declaration or
maturity promotion remains a separate maintainer decision based on deployment
requirements and reproducible evidence. Application examples do not create a
stable framework contract. A2A stays provisional and `EXPERIMENTAL`.
