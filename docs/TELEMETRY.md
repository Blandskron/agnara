# Transport-neutral invocation telemetry

Run the complete guide from a synchronized development checkout:

```bash
uv sync
uv run python examples/invocation_telemetry.py
```

[examples/invocation_telemetry.py](../examples/invocation_telemetry.py) attaches synchronous observers
to a compiled execution plan. It uses the core's public telemetry contracts,
without an exporter, network connection or protocol adapter. Its trusted local
principal is a fixture, not an authentication implementation.

Expected standard output:

```text
success: success; telemetry: success
denied: forbidden; telemetry: failure
invalid: invalid_input; telemetry: failure
failed: internal_failure; telemetry: failure
timeout: timeout; telemetry: timeout
cancelled: CancelledError; telemetry: cancellation
paired: 6; pending: 0; attempts: 6; correlation labels: 1
```

The intentional handler failure also produces the core's redacted operator log
on standard error. No input, returned value or exception diagnostic is printed
by the guide. Random event identities and measured durations are checked in
tests but omitted from standard output so that the output stays reproducible.

## Register observers at compilation

```python
from agnara.execution import ExecutionPlan, TelemetryHook

hooks: list[TelemetryHook] = [recorder]
plan = ExecutionPlan.compile(definition, dependencies, hooks=hooks)
```

Here `recorder`, `definition` and `dependencies` are application-owned objects
like those in the complete example. An observer implements
`on_invocation_start(InvocationStartEvent)` and
`on_invocation_terminal(InvocationTerminalEvent)`. Inheriting from
`TelemetryHook` is optional; the typed structural contract is sufficient.

Both callbacks accept one event and return `None` synchronously. They must not
block. Compilation rejects missing/non-callable callbacks and coroutine or
generator functions. The plan copies the hook collection into an immutable
tuple, but it does not freeze the observer's state. Keep its callbacks stable
after compilation.

The example's `FailingObserver` is an intentional fault fixture that raises an
ordinary `RuntimeError` in both callbacks. The runtime suppresses ordinary hook
exceptions, then continues to the later recorder and to execution. This does
not make throwing callbacks a production design: use separate observer-health
monitoring because those exceptions do not become invocation failures.
Process control and cancellation `BaseException`s are not suppressed.

## Pair events with invocation identity

`InvocationStartEvent.invocation_id` identifies one runtime invocation attempt;
the terminal event repeats it. The recorder keys its pending starts by this
identity, removes a start when its terminal arrives and records an unmatched
terminal with `None`. A start callback may have failed before recording state,
so terminal handling must tolerate that absence.

Every call in the example uses the same `tracking_id`, `batch-demo`. It is a
caller-provided correlation label, never a unique attempt key or authorization
input. Six calls still produce six distinct attempt identities with no pending
records. Fresh contexts in this example also have distinct `execution_id`s,
which each matching pair preserves. These identities have different meanings:
idempotent reuse can retain a logical execution identity while a later attempt
gets a new invocation identity. Nested invocation can additionally supply a
`parent_execution_id`; the direct calls here have no parent. See
[direct idempotency](DIRECT_IDEMPOTENCY.md) and
[nested invocation](NESTED_INVOCATION.md).

## Lifecycle outcomes and canonical results differ

For complete-result invocations, terminal `outcome` is `success`, `failure`,
`timeout` or `cancellation`. It describes execution at the observed runtime
boundary, not the full canonical failure category:

| Demonstrated call | Caller outcome | Telemetry outcome |
| --- | --- | --- |
| Successful handler | `Success` | `success` |
| Scope denial | `FailureCode.FORBIDDEN` | `failure` |
| Invalid input | `FailureCode.INVALID_INPUT` | `failure` |
| Unexpected handler exception | Redacted `FailureCode.INTERNAL_FAILURE` | `failure` |
| Expired deadline | `FailureCode.TIMEOUT` | `timeout` |
| Caller cancellation | Propagated `CancelledError` | `cancellation` |

A handler explicitly returning a canonical `Failure` completes without raising,
so the execution event may say `success` while the caller receives that failure.
Do not infer authorization decisions or canonical error codes from telemetry
outcomes. Observer callbacks are not policies and cannot grant access.

The start precedes policy, validation, dependencies and handler work for these
calls, and the terminal follows the execution scope's exit. Denied and invalid
calls have events without entering the handler. `duration_ns` measures the
observed runtime region with a monotonic clock, including applicable policy,
dependency and cleanup work and observer overhead in that region; it is not a
handler-only or network-latency benchmark. Complete-result events have
`units=None`. Streaming has its own terminal vocabulary and emitted-unit count,
and its duration spans the owned stream lifetime. This example does not
exercise streaming; see [HTTP SSE lifecycle](HTTP_SSE.md).

## Own observer state and publication

The recorder's dictionaries and lists belong to one demonstration on one event
loop. Callbacks do bounded in-memory updates and create no background tasks.
A collector shared across threads or other execution contexts must own its
synchronization, bounded buffering, retention and export lifecycle. The local
fixture is not evidence of free-threaded safety or a production collector.

Events hold declared capability identity, runtime identities, optional caller
correlation, and terminal duration/outcome/unit metadata. They do not carry
handler arguments, results, exception objects or dependency instances. This
limited shape is not an automatic publication approval: capability names and
caller-supplied tracking labels can still disclose sensitive information.
Review those values, cardinality and retention before logging or exporting,
and keep secrets out of correlation labels.

The separate `agnara-telemetry` distribution bridges these hooks to
application-supplied OpenTelemetry meters/tracers. Exporter configuration,
startup, flushing and shutdown belong to the application/adapter lifecycle;
the core does not manage them. See the
[telemetry package](../packages/agnara-telemetry/README.md). This guide claims no
exporter or backend interoperability.

## Evidence and ownership

[Guide tests](../tests/docs/test_telemetry_example.py) verify all six outcomes,
identity pairing, correlation reuse, ordinary observer fault isolation,
missing-start handling, event field boundaries, redaction, no handler effects
on denial/invalid input, container closure, no leftover tasks and execution
outside the checkout. Existing core telemetry tests cover callback contracts.

The example owns its cancelled invocation through a `TaskGroup`, handles that
child's cancellation at the caller boundary, and preserves cancellation of its
own caller. A separate five-second watchdog bounds the demonstration and is
not an invocation result. The application container closes in `finally`.
[The deadline guide](DEADLINES.md) explains cooperative cancellation limits.
No runtime/API or dependency changes are introduced.
