# ADR 0084 — Core Streaming Contract

- Status: Accepted
- Date: 2026-09-11
- Tracking: GitHub Issue #363
- Initiative: I2
- Answers: RFC 0009 questions Q1 to Q9, for the kernel only
- Related: RFC 0001, RFC 0009, ADR 0022, ADR 0025, ADR 0027, ADR 0031, ADR 0058,
  ADR 0068, ADR 0077

## Context

RFC 0009 frames the protocol-neutral streaming model and deliberately decides
none of it. Issue #362 was blocked in implementation review because writing
kernel code against an open RFC would have made the first implementation the
decision. This record answers that RFC's questions for the kernel and for
nothing else.

Transport projection is explicitly out of scope. HTTP SSE and WebSockets, MCP
progress notifications, A2A task events and the event adapter are consumers of
this contract and are decided separately, as RFC 0009 section 8 requires.

## Decision

### D1 — A streaming capability is declared *and* shaped (RFC 0009 Q1)

Streaming is both declared and verified. A capability declares `streaming=True` on
its authoring decorator, which becomes `CapabilityDefinition.streaming`. Its
handler must be an async generator function. `ExecutionPlan` rejects either
half without the other at compile time:

- `streaming=True` with a handler that is not an async generator function is a
  `DefinitionError`;
- an async generator handler without `streaming=True` is a `DefinitionError`.

The second rejection is the load-bearing one. Without it an async generator
would flow through `invoke_result` as an ordinary `Success` value, which is the
alternative RFC 0009 section 7 rejects, and it would do so silently.

Inference alone was rejected: a return annotation cannot distinguish a
generator from an iterable container or a user-defined awaitable, and an
`AsyncIterator[T]` annotation on a handler that returns a list would be a claim
the kernel could not check. Declaration alone was rejected because a
declaration with no verified shape is a second source of truth.

Synchronous iterators are out of scope. A synchronous producer cannot offer
pull-based demand without a thread or a buffer, and this record declines to
decide either.

The streaming flag is an execution-boundary property. It is deliberately not
added to the introspection snapshot here, because that is a versioned published
format (ADR 0045) and changing it is a separate, intentional migration.

### D2 — The canonical unit is an ordinary typed value (RFC 0009 Q2)

A stream carries the values its producer yields. There is no core event
envelope, no core event-kind vocabulary and no in-band control unit.

Lifecycle is carried out of band, by the stream's terminal state (D7), not by a
value in the sequence. A control event inside the data sequence would make
every consumer filter the sequence before using it, and the obvious vocabulary
to reach for would be SSE's or MCP's, which is the coupling RFC 0009 constraint
1 forbids.

Units are not schema-validated. The kernel compiles input schemas only;
`ExecutionPlan` has no output schema, for streaming and non-streaming
capabilities alike. Introducing one is output-schema work that applies to both
boundaries, and inventing it here for streams only would leave the kernel with
two different answers to one question. This is a known gap, recorded in
`docs/MATURITY.md` rather than left implicit.

### D3 — The execution boundary owns the stream, one-shot (RFC 0009 Q3)

`agnara.execution.open_stream(plan, context)` returns a `CapabilityStream`: an
owned, one-shot async context manager that is also an async iterator.

- `open_stream` performs no work and acquires nothing. A caller that obtains a
  stream and never opens it has leaked nothing, which answers the RFC's
  explicit question about an unstarted stream.
- Entering the stream runs the entire pre-output phase and stops there.
- Iterating pulls from the producer.
- Exiting closes the producer and then releases the invocation scope.

It is one-shot and single-owner. Re-entering an opened or closed stream raises
`InvocationError` rather than producing a second view of one producer. There is
no multicast: fan-out needs a buffering policy, and D4 refuses to have one.

### D4 — Backpressure is pull-based, and the kernel never buffers (RFC 0009 Q4)

`CapabilityStream.__anext__` awaits the producer directly. There is no queue,
no prefetch and no internal task. Demand is exactly the consumer's `__anext__`
calls, so a slow consumer slows the producer and nothing accumulates.

The RFC's questions about bound configuration and overflow behaviour therefore
have no kernel answer, because the kernel has no buffer to bound. An adapter
that must bridge the producer to a wire sender owns its buffer, must bound it,
and must document what overflow does. Dropping units silently is prohibited by
RFC 0009 Q4 and this record does not relax that.

### D5 — Cancellation propagates; the deadline bounds the whole lifetime (RFC 0009 Q5)

`asyncio.CancelledError` is never caught, never wrapped and never translated,
in the pre-output phase or during iteration. It reaches the producer's
`finally` through ordinary async generator finalization.

The invocation deadline is absolute and monotonic, so every await the stream
owns — the pre-output phase and each individual pull — is wrapped in
`asyncio.timeout_at(deadline)`. Bounding each await against the same absolute
instant bounds the whole stream lifetime, including time spent waiting on a
slow consumer, without a lifetime-scoped timeout object that would have to be
entered and exited across different awaits.

Teardown is **not** shielded. When a producer's `finally` awaits during
cancellation it may itself be interrupted; a producer that needs otherwise uses
`asyncio.shield` at the point it knows about. Shielding teardown in the kernel
would let one unresponsive producer make cancellation unhonoured, which
contradicts RFC 0009 constraint 3.

Core has no disconnect concept and gains none. A transport disconnect is an
adapter event; the adapter converts it into cancellation of the task that owns
the stream, or closes the stream. Both paths converge on generator cleanup.
There are no fire-and-forget producer tasks in core.

### D6 — Post-output failure is `StreamInterrupted` (RFC 0009 Q6)

The pre-output phase and the iteration phase fail differently, on purpose.

**Before the producer has been started**, the ordinary contract is untouched.
Policy denial, input validation, dependency construction and deadline expiry
raise the same exceptions they raise for a non-streaming invocation, and an
adapter projects them to the canonical `Failure` it already projects. Nothing
has been exposed, so nothing needs a new vocabulary.

**Once iteration has begun**, a failure raises `StreamInterrupted`, which
carries:

- `failure`: a canonical `Failure`, classified and redacted by exactly the
  rules `invoke_result` uses, so an unexpected producer exception becomes
  `internal_failure` with no message, path or traceback attached, and reaches
  the operator through the same log channel;
- `units_emitted`: how many units the consumer has already received.

`units_emitted` is what makes the distinction honest rather than nominal. A
producer that raises on its first pull has emitted nothing, and an adapter may
still project the ordinary canonical failure. A producer that raises after ten
units has not; RFC 0009 constraint 7 forbids presenting that as though no
output happened, and `units_emitted > 0` is the mechanical test for it.

The post-start causes stay distinguishable: a producer exception is
`internal_failure`, or the capability's own explicit code when it returned one;
a deadline is `timeout`; and consumer cancellation is not a `StreamInterrupted`
at all, because `CancelledError` propagates untouched, per D5.

### D7 — Terminal state is explicit, and iteration cannot infer it (RFC 0009 Q7, Q8)

`CapabilityStream.terminal` is `None` while the stream is live and a
`StreamTerminal` afterwards:

| Terminal | Meaning |
| --- | --- |
| `COMPLETED` | The producer was exhausted normally. |
| `INTERRUPTED` | The producer failed after iteration began. |
| `CANCELLED` | Cancellation propagated through the stream. |
| `TIMED_OUT` | The invocation deadline expired. |
| `ABANDONED` | The owner closed the stream before exhaustion. |

An empty successful stream is `COMPLETED` with `units_emitted == 0`, which is
distinct in kind from a failure before first output: the latter raises out of
the pre-output phase and never produces a terminal at all. RFC 0009 constraint
8 is satisfied by this field, not by counting units.

A producer cannot return a value after yielding: Python forbids a non-empty
`return` in an async generator, so the RFC's question does not arise.

Invocation resources are released when the stream is closed, exactly once, in
this order: the producer is closed first, then the invocation dependency scope
is torn down. The order matters because a producer's `finally` may still use
the dependencies it was given.

Telemetry reuses the existing hooks rather than growing a second model.
`InvocationStartEvent` is emitted when the stream is opened and
`InvocationTerminalEvent` when it is closed, so `duration_ns` spans the whole
stream lifetime. `InvocationTerminalEvent` gains `units`, the unit count for a
streaming invocation and `None` for a complete-result one. That is the minimum
safe attribute RFC 0009 Q8 asks for, alongside `outcome`, which carries the
`StreamTerminal` value. No payload is recorded, and no OpenTelemetry dependency
enters core. ADR 0058's guarded-cost rule is preserved: an application with no
hooks pays for none of it.

### D8 — What an adapter must preserve (RFC 0009 Q9)

This record decides no projection. It fixes what a projection may not change:

1. The adapter does not own the producer. It consumes a `CapabilityStream` and
   closes it; it never iterates a handler's generator itself.
2. Demand reaching the producer stays the adapter's actual demand. An adapter
   buffer must be bounded and its overflow behaviour documented.
3. A peer disconnect becomes cancellation or closure of the owning stream, not
   an abandoned producer.
4. After the adapter has exposed any unit, it must not present a later failure
   as though the invocation produced nothing.
5. Redaction is not re-decided. The adapter publishes
   `StreamInterrupted.failure` under the rules it already applies to a
   canonical `Failure` (ADR 0077).

An adapter conformance matrix belongs to each projection record, which must
state which terminals it can expose faithfully and which it must reject.

## Consequences

`invoke` and `invoke_result` now refuse a streaming plan with an
`InvocationError` instead of returning a generator object inside `Success`.
That is a behaviour change only for code that declared `streaming=True`, which
nothing could have done before this record.

The kernel gains four public names — `CapabilityStream`, `StreamInterrupted`,
`StreamTerminal` and `open_stream` — classified `provisional` like the rest of
the execution surface.

Left open, deliberately: output schema validation of units, the introspection
projection of the streaming flag, and every transport projection.

## Alternatives rejected

**A core event envelope with a fixed kind vocabulary.** Rejected by D2. The
vocabulary would have been borrowed from whichever transport shipped first.

**A lifetime-scoped `asyncio.timeout_at` held in an exit stack.** Correct only
while one task both opens and drains the stream, and silently wrong otherwise.
Per-await bounding against the same absolute deadline is equivalent and has no
such precondition.

**Returning `CanonicalResult[CapabilityStream]` from the pre-output phase.**
Rejected: a `Success` whose value is a live, owned resource re-creates the
ownership ambiguity RFC 0009 section 7 rejected, inside a wrapper that looks
safe.

**Shielded teardown.** Rejected by D5: it converts a producer bug into an
invocation that cannot be cancelled.
