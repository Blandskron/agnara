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
default. This proposal and its isolated prototype do not ship a supported
wrapper, application recipe or public API. Maintainer review is required
before a later implementation slice teaches an opt-in application pattern.

### D1 — Composition and authority

The host chooses the policy at composition, after installing its trusted
authentication result in the scope. A request cannot enable or disable it.
The policy reads no credentials, selects no principal, evaluates no capability
policy and classifies no business failure. The adapter and kernel retain all
their existing authentication, materialization, authorization, DI and output
contracts. Discovery metadata never grants authority.

The experiment wraps only HTTP POST calls to the dedicated surface. GET/card
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
Non-cancellation exceptions propagate through `TaskGroup`; the experiment does
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
the prototype adds no replacement timeout. Body size bounds do not establish
a read-time bound for a slow peer; hosts still own appropriate admission and
read/shutdown timeouts.

Cancelling work does not roll back effects already performed, establish
delivery, provide durable execution or make retries safe. Client message IDs
remain untrusted correlation values, not idempotency keys (ADR 0098 D9).
Applications must decide whether disconnect cancellation fits their operation
and persistence contracts. The policy grants no authorization, confirmation or
transactional guarantee.

## Evidence and boundaries

The stdlib-only [prototype](../../experiments/a2a/disconnect_policy.py) lives
outside every shipped package and application example. Nothing in the public
manifest, builder, dependencies or runtime defaults changes. It has no
production stability or host-support promise.

[Synthetic and loopback tests](../../tests/a2a/test_disconnect_policy_experiment.py)
cover no-read refusal, pass-through traffic, event identity/order, bounded
prefetch with a single reader, application/receive/send errors, external
cancellation including a race during policy-triggered cleanup, and a completed
response followed by a late disconnect. Tests assert that owned tasks end.

The existing pinned Uvicorn/h11 fixture additionally drives real mid-body and
post-entry socket closes with the prototype explicitly installed. Its kernel
deadline is 30 seconds, beyond the fixture's outer 15-second bound (and the
test's 10-second bound), so success requires peer-triggered cleanup rather
than eventual kernel timeout. The tests inspect handler/provider cleanup,
absence of a fabricated timeout reply, and a subsequent official-client call.
Real-host refusals additionally preserve HTTP 401 without an ASGI body read,
invalid input and policy denial before effects, and verified principal mapping.
The unwrapped host tests continue to assert the original deadline behavior.
CI on its final commit is the authority for cross-platform evidence; this
record itself does not certify a platform or production deployment.

## Alternatives

| Option | Benefit | Cost / disposition |
| --- | --- | --- |
| Deadline-only adapter behavior | Smallest ownership model; preserves current callers and semantics. | Work can continue until its cooperative deadline after a peer leaves. Retained as the default. |
| Explicit host-owned policy | Host controls receive ownership, deployment and effects policy without changing Agnara's public API. | Two owned tasks per monitored request and coordination with other receive consumers. Recommended for a separately reviewed opt-in pattern, backed by this reversible experiment. |
| Adapter/builder flag | A single adapter could govern and test a reusable option. | Adds a public contract and assumptions about upstream receive consumers, middleware and host cancellation. Deferred until host evidence and an API need justify it. |
| Core disconnect handling | Could appear uniform across transports. | A socket/ASGI event is protocol-specific, while core already propagates task cancellation. Rejected: no protocol dependency or new request type belongs in the kernel. |

No task/transport facade, core cancellation token or automatic classification
from capability metadata is introduced by selecting the host experiment.

## Follow-up implementation scope

1. Maintainer reviews the policy choice, receive ownership and effect/race
   limits in this Proposed record. Acceptance is a separate maintainer action.
2. If approved, create a scoped Issue for an application-owned recipe using
   governed imports. It must not import the experiment or change the existing
   builder's default; a new public export would require its own API proposal.
3. Validate that exact recipe from installed candidate wheels and over the
   pinned real host, including refusal before body reads, body limits,
   cancellation/error races, response completion and host shutdown. Keep the
   ordinary unwrapped host tests as a regression contract.
4. Only then consider any broader host/support or maturity decision on its
   own evidence. This proposal does not promote A2A beyond provisional and
   `EXPERIMENTAL`.
