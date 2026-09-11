# RFC 0009 — Protocol-Neutral Streaming Model

- Status: Draft
- Date: 2026-09-11
- Tracking: GitHub Issue #355
- Initiative: I2
- Supersedes: nothing
- Related: RFC 0001, ADR 0022, ADR 0027, ADR 0031, ADR 0068

## 1. Summary

Agnara has no streaming capability model. A handler can return an async
iterator today, but the kernel has no way to distinguish it from an ordinary
value, no invocation boundary owns its consumption, and no adapter can give it
consistent cancellation, backpressure, terminal-state or telemetry semantics.

This RFC frames the decisions required before streaming is introduced. It
decides none of them. Its eventual answers belong in one or more ADRs and must
be implemented with conformance tests before an adapter exposes streamed
capabilities.

## 2. Context

The current execution boundary deliberately has complete-result semantics.
`invoke_result()` yields either `Success(value)` or `Failure`, while direct
`invoke()` yields a Python value or raises. ADR 0022 leaves partial streaming
failure for a later design. The HTTP success boundary encodes its complete
representation before emitting `http.response.start` (ADR 0027), so it cannot
be reused as an accidental streaming implementation. MCP tool results and the
planned A2A and event adapters likewise project complete canonical outcomes.

That limitation is intentional, not a missing loop over an iterator. Once any
output has reached a caller, a later failure cannot replace it with the normal
canonical failure. A caller may also stop reading while the producer still
holds database cursors, files, dependency scopes or child tasks. Each transport
has different wire mechanics, but those facts are capability semantics and
must not be independently invented by HTTP, MCP, A2A or an event adapter.

I2 therefore precedes HTTP SSE and WebSockets, MCP progress, A2A streaming,
events and task progress. ADR 0068 assigns the resulting work to the execution
alpha; this RFC is its design entry point.

## 3. Scope

This RFC covers the protocol-neutral contract between a compiled capability,
the execution runtime and an adapter that consumes incremental output.

It must decide:

- what declaration and return shape identify a streaming capability;
- which boundary owns opening, iterating, closing and cancelling a stream;
- whether values, structured events, or both are the canonical units;
- how demand and slow consumers constrain producer progress;
- how cancellation, deadlines and consumer disconnect propagate;
- how a failure after emitted output is represented without pretending the
  complete-result model still applies;
- what completion means and what telemetry records across the full lifetime;
- which semantics adapters must preserve and which remain adapter-specific.

It does not design SSE, WebSockets, HTTP request-body streaming, MCP transport
extensions, A2A task events, event brokers, durable progress, resumability or
replay. Those are consumers of a settled kernel contract. It also does not
alter non-streaming `Success`/`Failure`, direct invocation, schema adapters,
or the task model.

## 4. Constraints and invariants

Any proposal answering this RFC must preserve these constraints.

1. **Core remains transport-neutral.** No HTTP status, ASGI event, JSON-RPC,
   MCP SDK or A2A SDK type belongs in the kernel stream contract.
2. **A stream has one explicit owner.** The owner is responsible for closing
   it on normal completion, failure, timeout, cancellation and abandoned
   consumption. Ownership cannot be an adapter convention hidden in a loop.
3. **Cancellation remains control flow.** `CancelledError` must propagate; it
   is not converted into a successful terminal event or a canonical failure.
4. **Effects and policy remain pre-output.** Capability policy, input
   validation and dependency construction must complete before a producer can
   emit its first unit. A stream cannot become a policy-bypass path.
5. **Dependencies have bounded lifetime.** Invocation-scoped providers remain
   alive while the stream needs them and teardown happens exactly once after
   ownership ends.
6. **Backpressure is observable, not wishful.** An unbounded internal buffer
   is not an implementation of slow-consumer handling. If a contract permits
   buffering, its bound and overflow consequence must be explicit.
7. **No false atomicity.** After an adapter has exposed output, it must not
   present a late error as though no output happened. The model needs a
   distinct terminal outcome for this case or must make the partial history
   visible by another precise mechanism.
8. **Completion is distinguishable from interruption.** A consumer, adapter
   and telemetry hook must be able to tell normal completion, producer failure,
   deadline expiry and cancellation apart without inferring from missing bytes.
9. **Streams are not durable tasks.** Process survival, replay, checkpoints,
   resume tokens and delivery guarantees stay outside this RFC.

## 5. Open questions

### Q1 — What makes a capability streaming?

Is streaming declared explicitly, inferred from an `AsyncIterator[T]` return
annotation, represented by a distinct return wrapper, or some combination?
Inference keeps authoring concise but can make a generator, iterable container
or user-defined awaitable ambiguous. An explicit declaration is compile-time
auditable but risks a second source of truth beside the return annotation.

The answer must specify compile-time rejection cases, schema implications and
whether sync iterators are in scope. It must not make an adapter-specific
decorator the canonical declaration.

### Q2 — What is the canonical unit?

A sequence of values is sufficient for token-like output, while structured
events can carry progress, data, warnings and terminal information. Choosing
only raw values forces adapters to invent lifecycle events; choosing only an
event envelope may make ordinary generators needlessly ceremonial.

The decision must state whether a stream can carry arbitrary typed values,
whether event kinds form a core vocabulary, how each unit is schema-validated,
and whether control events are separate from application data. It must avoid
turning an HTTP event format or MCP notification into the core vocabulary.

### Q3 — Where does consumption live?

Possible boundaries include an execution API returning an owned stream object,
an adapter-facing async iterator produced from a compiled plan, or a runtime
operation that accepts a consumer callback. They differ on who retains the
invocation dependency scope, where generator finalization occurs, and whether
two consumers can accidentally read one producer.

The answer must make one-shot versus multicast behavior explicit. It must also
define what happens if a caller obtains a stream and never begins iteration.

### Q4 — What is the backpressure contract?

Python async iteration naturally provides pull-based demand when the consumer
awaits each next item, but adapters may need buffering to bridge a producer and
a wire sender. A synchronous producer, a fan-out design or a callback API can
lose that property.

The design must define which layer may buffer, whether any kernel buffer is
bounded, how a bound is configured, and whether overflow blocks, fails,
cancels or drops. Dropping is not acceptable as an undocumented default for a
capability that might report financial or safety-relevant progress.

### Q5 — How do cancellation, deadline and disconnect interact?

A caller may cancel directly; an adapter may detect a peer disconnect; a
capability deadline may expire; and application shutdown may cancel owned
work. These paths must converge on generator cleanup while retaining their
different observability meaning.

The answer must say whether a transport disconnect is normalized into an
execution cancellation signal, how it reaches the producer, which exception
or state a producer observes, and how teardown is shielded only as far as
needed for correctness. It must preserve structured concurrency and prohibit
fire-and-forget producer tasks in core.

### Q6 — How is post-output failure represented?

Before the first emitted unit, an invocation can still yield the ordinary
canonical `Failure`. Afterwards, an adapter cannot replace sent data with that
result. Candidate designs include a protocol-neutral terminal event, an
adapter-visible terminal state outside the data sequence, or a model that
declares a stream simply interrupted and requires adapters to expose the cause
according to their protocol.

The answer must distinguish a producer exception, validation failure of a
later unit, timeout and consumer cancellation. It must specify what is safe to
publish, preserve redaction rules for unexpected exceptions, and define
whether an adapter may emit a terminal error after partial data.

### Q7 — What completes a stream?

Natural exhaustion, an explicit completion unit, an early consumer stop and a
transport close are not equivalent. Completion must define the point at which
invocation resources are released and terminal telemetry is recorded.

The answer must decide whether completion can carry final metadata, how an
empty successful stream differs from a failed-before-first-output invocation,
and whether a producer is allowed to return a value after yielding.

### Q8 — How does telemetry span the lifetime?

Current telemetry surrounds a complete invocation. A stream can be long lived
and can emit many units, so one span per unit may be too costly and one span
with no useful attributes may be too vague.

The decision must define start and terminal events, minimum safe attributes
(for example unit count and terminal classification), duration ownership and
sampling expectations. It must not place an OpenTelemetry SDK dependency in
the core or record payloads by default.

### Q9 — What must adapters preserve?

HTTP, MCP, A2A and event transports may differ in framing, reconnect behavior,
ordering and user-visible errors. The kernel contract must be narrow enough
that adapters retain those differences while all preserve the same producer
ownership, cancellation, backpressure and terminal semantics.

The eventual ADR must state an adapter conformance matrix: which canonical
events/states each adapter can expose faithfully, what an adapter must reject,
and which richer transport features remain extensions rather than kernel
requirements.

## 6. Evaluation criteria

Before accepting an answer, compare it against these scenarios:

- a generator using an invocation-scoped database cursor completes normally;
- a slow client consumes one unit at a time without unbounded buffering;
- a client disconnects halfway through and the generator's cleanup runs;
- a deadline expires before first output and after several units;
- a producer raises an unexpected exception after output, without leaking its
  message;
- a consumer stops early without leaving a background task or provider alive;
- two adapters project the same capability without changing the capability's
  policy, effects or result semantics;
- a non-streaming capability continues to use the existing result boundary
  unchanged.

An answer that cannot state expected observations for each scenario is not
ready for an ADR. The resulting implementation must add focused kernel tests
and adapter conformance tests before declaring streaming available.

## 7. Alternatives rejected now

**Let every adapter implement streaming independently.** Rejected because the
first adapter would define cancellation and partial failure accidentally, and
later adapters would either duplicate or contradict it.

**Treat an async iterator as an ordinary `Success` value.** Rejected because
there is no owner of iteration or cleanup, output validation happens too late,
and `Failure` cannot describe a late error honestly.

**Buffer every stream to recover complete-result semantics.** Rejected because
it defeats streaming for large or unbounded results and transfers memory risk
to the framework.

**Build durable progress and replay first.** Rejected because those properties
need persistence and task identity; they cannot settle the much smaller
in-process stream lifetime contract.

## 8. Decision path

This RFC remains open until a maintainer accepts answers to the questions above
through one or more ADRs. The ADRs should separate the core stream contract
from any transport projection so that an unresolved SSE, MCP or A2A feature
cannot delay a kernel decision unnecessarily.

After implementation, update `docs/MATURITY.md` with only verified behavior,
and update this RFC's index lifecycle to reflect the settled state. No adapter
may claim streaming support merely because it can serialize an async iterator.
