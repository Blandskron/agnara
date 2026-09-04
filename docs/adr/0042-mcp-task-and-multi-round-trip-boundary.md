# ADR 0042 — MCP Task and Multi-Round-Trip Boundary

- Status: Proposed
- Updated: 2026-09-04
- Tracking: GitHub Issue #174

## Decision

For the pinned `2026-07-28` baseline, Multi Round-Trip Requests are the only
resumption mechanism `agnara-mcp` implements. Agnara does not implement,
advertise or claim the Tasks extension.

A resumed round never carries authorization. `requestState` protects the
continuity of one round; verifier-backed `ConfirmationEvidence` remains the
only thing that may satisfy a `ConfirmationPolicy`.

## Rationale

### Tasks left the pinned baseline

Tasks were introduced in `2025-11-25` and removed from the core specification
in `2026-07-28`, where they continue as an opt-in extension. The pinned
official SDK reflects that split precisely: `mcp_types` defines `Task`,
`CreateTaskResult`, `GetTaskRequest`, `CancelTaskRequest`,
`GetTaskPayloadRequest`, `ListTasksRequest` and `TaskStatusNotification` as
types only, and their methods are absent from the request and notification
unions the server dispatches. `mcp` 2.1.1 ships no task store, no task
lifecycle and no `tasks/*` handler; `mcp.server.extension` names `tasks/get`
only as an example of a method some future extension could serve.

Implementing Tasks would therefore mean Agnara authoring an extension and its
entire retention, cancellation, polling and status-notification lifecycle
before its own tool invocation, conformance suite and benchmarks exist. That
inverts the E7 order and would produce a compatibility claim with no
conformance evidence behind it, which ADR 0010 forbids.

`Tool.execution` and its `task_support` marker are `2025-11-25`-only fields
removed in `2026-07-28`. Agnara's tool projection never sets them, and must
not begin doing so to signal task capability.

### MRTR is the mechanism the baseline actually defines

In `2026-07-28`, an interactive request returns `InputRequiredResult` in place
of its normal result, carrying server-assigned `input_requests` and an opaque
`request_state`. The client fulfills the requests and retries *the original
request*, echoing the responses and the state verbatim. There is no
server-to-client back-channel and no separate resumption method.

The carrier set is closed: `tools/call`, `prompts/get` and `resources/read`
are the only methods whose results may carry `requestState`. Agnara exposes
capabilities as tools only, so `tools/call` is the sole carrier in scope for
E7 and the only one Agnara may mint state for.

## Request-state protection

The SDK provides `RequestStateBoundary`, middleware that seals every outgoing
`requestState` and verifies every inbound echo before any interceptor or
handler runs, so a handler only ever sees plaintext the server minted. Its
envelope binds the protocol version, issued-at and expiry timestamps, the
method, the request target, a digest of the arguments, an audience and a
principal claim. Verification failure answers `-32602` with a frozen
`"Invalid or expired requestState"` message and logs the real reason
server-side only.

Three properties of that boundary constrain Agnara directly.

**It is not installed on the tier Agnara builds on.** Only
`mcp.server.mcpserver.MCPServer` appends the middleware. `agnara-mcp` builds
its discovery surface on the lowlevel `mcp.server.Server`, whose `extensions`
attribute is an advertisement map rather than a composition tier. Any Agnara
surface that mints `requestState` must append `RequestStateBoundary`
explicitly, with an explicit `default_audience` naming the Agnara server
identity. Omitting it does not degrade protection; it removes it, leaving
client-supplied state to reach a handler as trusted plaintext.

**Its convenience default is single-process.**
`RequestStateSecurity.ephemeral()` mints a key held only by the current
process, so state minted before a restart or by another worker is rejected.
Agnara must require an explicit shared key ring for any multi-instance
deployment and must never present an ephemeral policy as a production
default.

**It does not provide replay protection.** The envelope carries expiry and
binding claims but no single-use marker and no consumed-token store, so an
identical round bound to the same method, target, arguments and principal
remains replayable until its TTL elapses (600 seconds by default). Round
integrity is not invocation-level replay safety. ADR 0024 already assigns
replay protection to the `ConfirmationVerifier`, and this decision does not
move it.

## Confirmation boundary

`ElicitResult.action` is one of `accept`, `decline` or `cancel`, and its
`content` is the submitted form data. Both are client-supplied input. Neither
an `accept` action nor a `confirmed: true` value is evidence of anything, and
Agnara must not construct `ConfirmationEvidence` from them.

A future resumption path must, on the retry round:

- accept `requestState` only through a verified boundary;
- match echoed `input_responses` to the keys the same round assigned;
- re-evaluate the core policy for the retried invocation rather than treating
  the presence of state as prior approval;
- call `ConfirmationVerifier.verify` with the capability identity, the
  invocation and the mapped principal, exactly as direct invocation does;
- map a `decline` or `cancel` action to a canonical refusal rather than to a
  transport error or a silent success.

## Scope

This decision does not implement resumption, tool invocation, elicitation
response handling or any `requestState` minting. It records the boundary that
E7.8 conformance and any later invocation work must respect. E7.6 remains the
only shipped interaction behavior: a one-way projection of a canonical
confirmation requirement into an `InputRequiredResult` form elicitation, with
no state and no resumption.

Agnara advertises no extension identifier under `ServerCapabilities.extensions`
as a result of this decision.

## Consequences

Clients that expect task-augmented execution against an Agnara server will
not find it, and must use the MRTR flow the pinned revision defines. Release
notes must state that Tasks are unsupported rather than leaving it inferred
from SDK capability, per ADR 0010.

Should Tasks be revisited, it becomes its own backlog item, ADR and
conformance suite, starting from an extension identifier and a retention
policy rather than from a field on a tool definition.

## Evidence

- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
- https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation
- https://py.sdk.modelcontextprotocol.io/handlers/multi-round-trip/
- https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp/server/request_state.py
- https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp/server/extension.py
- https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp_types/_types.py
- https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp_types/methods.py
