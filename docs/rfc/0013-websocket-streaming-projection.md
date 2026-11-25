# RFC 0013 — WebSocket streaming projection boundary

- Status: Open research; no implementation decision
- Date: 2026-11-24
- Tracking: GitHub Issue #817
- Initiative: Protocol Projections
- Follow-up: [WS-01 evidence](../../experiments/websocket/README.md)
- Related: ADR 0026, ADR 0029, ADR 0041, ADR 0070, ADR 0071, ADR 0084, ADR 0085, ADR 0086, RFC 0009

## 1. Purpose and current boundary

Define the smallest bounded WebSocket projection that preserves Agnara's
capability, security and stream-ownership semantics before any adapter API or
ASGI `websocket` scope handler is designed.

Today:

- The kernel implements pull-based streaming capabilities through `open_stream`
  and `CapabilityStream` (ADR 0084, ADR 0086).
- `agnara-http` implements complete-result routes (`ADR 0027`, `ADR 0071`) and
  unidirectional HTTP Server-Sent Events via `Http.sse` (ADR 0085), handling
  ASGI `http` and `lifespan` scopes only (`ADR 0029`, `ADR 0041`).
- [Subsystem maturity](../MATURITY.md) lists `WebSockets` as `PLANNED` with no
  `websocket` scope handling and no accepted design decision.

This RFC adds no runtime code, no ASGI `websocket` handler, no public
`agnara_http` export and no protocol support claim. Bidirectional chat sessions,
pub/sub rooms, multiplexed RPC channels, binary media streaming and durable
replay remain out of scope.

## 2. Protocol and ASGI boundary constraints

Facts from RFC 6455 and the ASGI 3.0 HTTP/WebSocket specification shape any
future projection:

1. **Handshake precedes `websocket.accept`.** An ASGI server delivers
   `{"type": "websocket.connect"}` before switching protocols. Closing with
   `websocket.close` prior to `websocket.accept` rejects the HTTP upgrade (for
   example on invalid `Origin`, missing authentication or failed pre-output
   authorization) without entering application framing.
2. **Cross-Site WebSocket Hijacking (`Origin`) is host security.** Unlike CORS
   for `fetch`, browsers send cookies automatically on WebSocket upgrades and do
   not block handshake establishment by response header alone. Pre-accept checks
   must keep authentication and origin/host verification at a trusted host
   boundary rather than weakening policy checks.
3. **Disconnect arrives via `websocket.receive`.** After `websocket.accept`,
   the server signals peer closure through
   `{"type": "websocket.disconnect", "code": ...}` read from `receive()`, not
   only when sending a frame. Monitoring disconnect while awaiting a slow
   `CapabilityStream` producer therefore requires structured concurrency.
4. **URL credentials and large payloads belong outside query strings.** Putting
   bearer secrets or large JSON payloads in handshake query parameters risks proxy
   and access-log leakage as well as URL length limits.
5. **Close codes are constrained metadata.** RFC 6455 reserves narrow status
   ranges (`1000` normal closure, `1008` policy violation, `1011` unexpected
   condition). Application failures and redaction rules cannot rely solely on a
   numeric close code if structured failure envelopes are required.

## 3. Candidate projection shapes

| Option | Boundary | Fit with Agnara invariants | Tradeoff |
| --- | --- | --- | --- |
| A. Handshake-bound server stream | Handshake binds path/header/query inputs (`Http.sse`-style), validates auth/origin/policy before `accept`, pulls `open_stream`, emits framed units until `terminal`/`interrupted`, then closes. | Preserves single-invocation ownership, pre-accept refusal and pull demand without a message-dispatch state machine. | Cannot accept a large JSON body cleanly unless paired with short tokens or Option B. |
| B. Initial-frame-triggered server stream | `websocket.accept` after origin/auth check, read **one** bounded initial JSON input message via `websocket.receive` with timeout, enter `open_stream`, then emit server stream and close. | Keeps structured JSON inputs (matching `BindingSource.BODY`) out of URLs while preserving one invocation per connection. | Auth still happens at handshake before `accept`, while input validation occurs after `accept` and must map rejections onto close/error frames cleanly. |
| C. Bidirectional / multiplexed session | Long-lived connection dispatching multiple capability calls or bi-directional async iterators on one socket. | Requires a second protocol runtime, per-frame correlation, session state and multi-invocation lifecycle beyond `CapabilityStream`. | Deferred; incompatible with single-invocation ADR 0084 boundaries. |

Options A and B are both narrower than Option C and map onto one `open_stream`
invocation per WebSocket connection. Deciding between A, B or a sequenced path
starting with A (or B) belongs to a follow-up ADR after feasibility evidence.

## 4. Invariants any decision must preserve

Any ADR answering this RFC MUST uphold existing framework guarantees:

1. **Core neutrality.** `agnara-core` imports no WebSocket or ASGI server library
   and introduces no WebSocket close code, frame type or subprotocol concept.
2. **Pre-output authority and redaction.** Authentication, scope/business policy,
   schema validation and dependency injection complete before any output unit is
   transmitted. Internal failure diagnostics are redacted before wire framing.
3. **One explicit stream owner.** `open_stream` owns `CapabilityStream` closure
   and `Scope.INVOCATION` dependency teardown on completion, failure, timeout and
   peer disconnect.
4. **Bounded pull-based demand.** No unbounded send buffer or producer prefetch;
   a slow receiver exerts backpressure on `await stream.__anext__()` and oversized
   frames are rejected explicitly against a configured limit.
5. **Cancellation propagation and zero leaked tasks.** If `websocket.receive`
   reports `websocket.disconnect` while the producer is suspended, the adapter
   cancels the producer task cleanly, awaits same-loop resource teardown and leaves
   no orphaned background tasks.
6. **No false atomicity after output.** Once a first data frame has been sent to
   the peer, a subsequent producer error maps to an explicit interruption signal
   rather than pretending the stream never started (ADR 0084, ADR 0085).
7. **Same-loop lifespan ownership.** Shared `SINGLETON` resources remain owned by
   the ASGI `lifespan` scope (ADR 0029), never closed prematurely by an individual
   WebSocket disconnect.
8. **Separation from OpenAPI HTTP routes.** Like `Http.sse` (ADR 0085 D1), a
   WebSocket exposure must not emit misleading HTTP request/response OpenAPI
   operations; it participates in neutral `CompiledExposure` introspection instead.

## 5. Open questions for the follow-up ADR

Any implementation proposal must resolve Q1 through Q9 explicitly:

- **Q1 — Package and API placement:** Should WebSocket projection live as an
  explicit method on `agnara_http.Http` (for example `Http.websocket(...)`)
  reusing the existing ASGI entry point, or in a separate adapter distribution?
- **Q2 — Handshake security and `Origin` policy:** Does the adapter enforce an
  explicit host-configured allowed-origin check / CSRF boundary before
  `websocket.accept`, and fail closed if unconfigured?
- **Q3 — Input binding model:** Should the first slice restrict inputs to
  handshake bindings (Option A), accept one bounded initial JSON request frame
  (Option B), or forbid body-style arguments initially?
- **Q4 — Frame schema and close codes:** How are `unit`, `StreamTerminal` and
  `StreamInterrupted` encoded in JSON text frames, what is the default
  `max_frame_bytes` budget, and which RFC 6455 close codes correspond to policy
  denial, invalid input, timeout and internal failure?
- **Q5 — Disconnect vs. pull-demand coordination:** How does the adapter monitor
  `websocket.receive` for `websocket.disconnect` alongside `stream.__anext__()`
  using `asyncio.TaskGroup` so client-sent unexpected frames or sudden closes
  never hang or leak tasks?
- **Q6 — Backpressure and slow-client bounds:** How does `await send(...)` interact
  with outbound send timeouts and cooperative `deadline` enforcement so a stalled
  socket cancels the invocation within bounded wall-clock time?
- **Q7 — Subprotocol negotiation:** Should subprotocols remain unsupported or
  require exact opt-in declaration without weak fallback?
- **Q8 — Introspection and discovery metadata:** What adapter target/detail
  fields belong in `CompiledExposure` and `DiscoveryVisibility` without leaking
  internal bindings?
- **Q9 — Required evidence gate:** Before moving `WebSockets` from `PLANNED` to
  `EXPERIMENTAL` or `IMPLEMENTED`, what in-memory ASGI conformance tests plus
  real server/client loopback evidence (for example Uvicorn + a pinned
  WebSocket client testing disconnect during suspended producer wait, invalid
  `Origin`, oversized frame, concurrent isolation and `all_tasks()` parity) are
  mandatory?

## 6. Next step

A future feasibility Issue may build a throwaway in-process ASGI and Uvicorn
loopback experiment (following the `experiments/` pattern used before ADR 0098
and ADR 0101) to validate Q2–Q6 and Q9 before drafting an ADR for maintainer
review.
