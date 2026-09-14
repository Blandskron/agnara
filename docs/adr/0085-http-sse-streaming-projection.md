# ADR 0085 — HTTP Server-Sent Events Projection of Capability Streams

- Status: Accepted
- Date: 2026-09-12
- Tracking: GitHub Issue #368
- Initiative: I2 Streaming
- Answers: RFC 0009 Q9 for HTTP SSE
- Related: ADR 0027, ADR 0028, ADR 0031, ADR 0072, ADR 0077, ADR 0084 and RFC 0009

## Context

ADR 0084 supplies the transport-neutral stream boundary: a declared async
generator is opened once, demand reaches it by pull, cancellation propagates,
and a late failure is never represented as though no unit was exposed.  It
deliberately decides no wire projection.  `agnara-http` currently has the
opposite, complete-result boundary: it serializes all JSON before emitting
`http.response.start` (ADR 0027).  Treating an async iterator as just another
JSON response would silently drop both designs' ownership and partial-failure
guarantees.

SSE is the first HTTP response-stream projection because it is one-directional
HTTP output and can preserve the core's pull model without creating a core
event vocabulary.  It is not a decision about WebSockets, request-body
streaming, replay, task progress, or durable delivery.

## Decision

### D1 — SSE is an explicit HTTP exposure, not an implicit response type

The public HTTP composition API gains an explicit `Http.sse(path, capability,
*bindings, ...)` declaration.  It is the only first-release SSE spelling.
Compilation requires all of the following:

- its method is exactly `GET`;
- the capability's compiled plan has `streaming=True`;
- its bindings are limited to path, query, header and cookie sources; and
- it is not given `OpenApiOperation` metadata.

The inverse is also rejected: an ordinary `get`, `post`, `put`, `patch`,
`delete` or `route` exposure cannot target a streaming plan.  That preserves
the existing complete JSON response boundary and makes the HTTP choice visible
where the exposure is declared.  `HEAD` does not fall back to an SSE `GET` and
answers the ordinary `405` before a stream opens; a response with no body is
not a useful or honest consumption of a one-shot producer.

`BODY`, `FORM` and `UPLOAD` are excluded because browser `EventSource` uses a
GET request and this projection supplies no separate request-body streaming
contract.  A caller that needs a custom client may use the non-body bindings,
but gains no alternate verb, request format or content negotiation from SSE.

### D2 — One yielded value becomes one `message` SSE event carrying JSON

The adapter consumes `CapabilityStream`; it never obtains or iterates the
handler's generator directly.  Each yielded value is first projected through
the existing HTTP JSON-value serializer, then encoded as one compact UTF-8
JSON value, and framed as:

```text
data: <one JSON value>\n\n
```

No `event` field is sent for data, so an EventSource consumer receives the
standard `message` event.  The core unit has no SSE name, id, retry interval,
sequence number or envelope.  The first projection emits no `id` or `retry`
field and gives `Last-Event-ID` no automatic meaning: reconnecting starts a
new ordinary capability invocation, not resumption or replay.

The exposure owns a `max_event_bytes` limit, defaulting to the existing
HTTP body ceiling of 1 MiB.  It is checked after deterministic JSON encoding
and before the event is sent.  There is no queue, prefetch or aggregation;
at most one encoded event is held by the adapter at once.  A larger unit is a
response-projection failure, not a reason to truncate or silently drop data.

### D3 — The HTTP response begins only after the first pull is representable

After normal request binding, the adapter builds its `ExecutionContext` as it
does today and enters `open_stream(..., input_materializer=materialize_json)`.
Policy evaluation, materialization, validation, dependency acquisition and
producer creation therefore remain pre-output.  Any failure there is classified
by the same canonical failure rule as `invoke_result` and is sent as the
ordinary, complete RFC 9457 problem response.

The adapter then pulls and serializes the first unit before it sends
`http.response.start`.  If that first pull fails, times out, or cannot be
serialized, no unit was exposed and the ordinary RFC 9457 response remains
available.  An empty producer is also a successful first result: the adapter
then starts the SSE response and sends its terminal event described below.

The successful response is:

```text
200
content-type: text/event-stream; charset=utf-8
cache-control: no-store
```

It has no `content-length`, no adapter-owned `connection` or transfer-encoding
header, and no compression, CORS or proxy-buffering policy.  Those remain
server, proxy or outer-ASGI-middleware concerns, exactly as ADR 0072 assigns
them.  An SSE declaration is its own representation contract, so it does not
inspect `Accept` or add general content negotiation.

### D4 — Terminal events make a completed stream distinguishable from a late failure

SSE connection close alone cannot truthfully distinguish normal exhaustion
from a producer failure.  After any started SSE response, the adapter emits
one final, adapter-specific event whenever the connection is still writable:

```text
event: agnara.terminal
data: {"outcome":"completed","units":2}

```

`outcome` is the corresponding `StreamTerminal` value and `units` is the
number already sent as data events.  A normal empty stream therefore ends with
`completed` and `units: 0`, not an ambiguous empty connection.

For `StreamInterrupted` after data has been sent, the terminal payload also
contains a `problem` member.  Its value is the existing redacted RFC 9457 JSON
projection of `StreamInterrupted.failure`; it is data inside the SSE event,
not a replacement HTTP response or a second status line.  An unexpected
exception consequently has the same fixed internal-failure detail it would
have in an ordinary HTTP response and never exposes exception text, traceback,
dependency values or a request fragment.

An adapter-local failure while serializing a later unit, including
`max_event_bytes`, is treated the same way: it logs only an operational,
non-value diagnostic, emits a redacted `interrupted` terminal if possible,
and closes the owned stream.  Core telemetry records the actual stream close
state; the SSE terminal records that the projection interrupted the wire.  No
payload is retried, truncated or added to a log.

No terminal can be promised after client disconnect, application cancellation
or an `OSError` from ASGI `send`: the peer is already unavailable.  In those
paths the stream is closed or cancelled and only its core terminal telemetry
records the result.

### D5 — Actual ASGI send demand is the stream's demand; disconnect has structured ownership

The response pump performs exactly this order for every data event: pull one
unit, encode one unit, await one `http.response.body` send.  The next pull
does not begin until that send returns.  Consequently a slow client or server
send buffer slows the producer without an unbounded adapter buffer.

Once the response has begun, the adapter owns one structured disconnect watcher
for the same ASGI request.  It waits for `http.disconnect`; on receipt it
cancels the response pump, which propagates `CancelledError` into the
`CapabilityStream` and its producer cleanup.  The watcher is cancelled and
joined when normal consumption ends.  An `OSError` raised by `send` is handled
as the same peer-disconnect condition and closes the stream without logging a
server error.  The watcher and pump are joined before the ASGI call returns;
there is no fire-and-forget task, second producer consumer, or background
queue.

The request deadline starts after binding, as it does for complete HTTP
responses.  Once the stream is open, ADR 0084 applies the same absolute
deadline to every pull, so it bounds the full response lifetime.  A timeout
before the first data event remains a normal `504` problem; after data it is
an SSE terminal with `outcome: "timed_out"` and a redacted timeout problem.
Application shutdown cancellation continues to propagate and is never changed
into a successful terminal event.

### D6 — Discovery, OpenAPI and replay do not gain accidental promises

The existing OpenAPI projection describes complete JSON representations and
has no reviewed schema for arbitrary stream units or the terminal event.
`Http.sse` therefore rejects `OpenApiOperation` and an SSE route is absent
from generated OpenAPI until a separate response-schema and documentation
decision can describe both the data and terminal events truthfully.  The
versioned protocol-neutral introspection snapshot also remains unchanged;
adding a streaming field is its own migration, as ADR 0084 already decided.

SSE reconnection is a client transport behaviour, not an Agnara delivery
guarantee.  The projection neither resumes an execution nor deduplicates a
new one.  Existing policy, confirmation and effect rules still run before
each invocation; I3 will decide operational identity and idempotency rather
than this transport fabricating them.

## Conformance matrix

| Core fact | HTTP SSE projection |
| --- | --- |
| Pre-output failure | Complete RFC 9457 problem; no SSE response starts. |
| First-pull failure with zero units | Complete RFC 9457 problem; response start was delayed. |
| Data unit | One UTF-8 JSON `message` event; one pull per completed send. |
| Normal completion, including empty | `agnara.terminal` with `completed` and exact unit count, then final ASGI body. |
| Producer failure after output | `agnara.terminal` with `interrupted`, exact unit count and a redacted problem, then final ASGI body. |
| Deadline after output | `agnara.terminal` with `timed_out`, exact unit count and a timeout problem, then final ASGI body. |
| Client disconnect / send failure | No wire terminal; cancel or close the owned stream and await cleanup. |
| Application cancellation | No wire terminal; propagate cancellation unchanged. |
| Replay, `Last-Event-ID`, custom event kinds, WebSockets | Not supported by this projection. |

## Consequences

The future implementation adds HTTP-private streaming dispatch and focused
ASGI conformance tests; it does not add SSE types, ASGI messages, event names
or response statuses to `agnara`.  It will need an adapter-facing reuse of the
already shared canonical exception-to-`Failure` classifier for pre-output
stream failures.  That reuse must be exposed or factored deliberately rather
than importing the core's private `_outcome` module from `agnara-http`.

The implementation must update the public API inventory for `Http.sse`,
`docs/MATURITY.md` only after tests demonstrate the projection, and
`HTTP_COMPOSITION.md` to replace its SSE deferral.  Until then, no public
route claims SSE support.

## Alternatives rejected

**Make every streaming HTTP route SSE automatically.** Rejected: a capability
can be projected through more than one adapter and a transport representation
belongs to an explicit exposure, not the capability declaration.

**Start the response when the stream opens.** Rejected: a first-pull failure
with zero emitted units would lose the ordinary RFC 9457 response despite ADR
0084 explicitly allowing the adapter to preserve it.

**Use connection close as the terminal signal.** Rejected: it makes clean
completion, timeout and producer failure indistinguishable to the client.

**Use SSE `id` / `Last-Event-ID` as execution identity.** Rejected: those are
transport replay tokens, not the cross-transport operational identity I3 must
decide.

**Run the disconnect reader as an unowned background task.** Rejected: it
would turn a peer close into a leaked producer and violate ADR 0084's explicit
ownership rule.

## Revisit when

Revisit the OpenAPI exclusion when a response-unit schema and a versioned
introspection migration are accepted.  WebSockets need a separate ADR because
they have a bidirectional connection and distinct close semantics.  Replay,
resumption and durable progress wait for I3 and durable-execution design.
