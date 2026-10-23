# Direct Python streaming and resource ownership

Run the complete [example](../examples/direct_streaming.py) from a synchronized
development checkout with Python >=3.14:

```bash
uv sync
uv run python examples/direct_streaming.py
```

The example uses only governed public imports. Each case compiles a capability,
binds an invocation-scoped provider, creates a container on the running event
loop and closes it in `finally`. The resource and trusted principal are local
fixtures; no database, network connection or production authentication is used.
This guide describes the current checkout, including unreleased output fixes;
it does not establish the behavior of the published 1.0.3 wheel.

Expected standard output (the deliberately failing cases also emit runtime
log warnings):

```text
completed: units=[0, 1] terminal=completed failure=None
abandoned: units=[0] terminal=abandoned failure=None
denied: units=[] terminal=not_started failure=forbidden
invalid_input: units=[] terminal=not_started failure=invalid_input
first_failure: units=[] terminal=interrupted failure=internal_failure
late_failure: units=[0] terminal=interrupted failure=internal_failure
invalid_output: units=[0] terminal=interrupted failure=internal_failure
```

`not_started` is the example's display label for `stream.terminal is None`.
It is not another member of `StreamTerminal`.

## Declare a unit contract and own consumption

The handler is an async generator declared with `streaming=True` and
`output=int`. The output contract validates each actual yielded value; its
`AsyncIterator[int]` annotation alone does not enable output validation.
Use `open_stream` for this boundary, rather than `invoke_result`:

```python
from agnara.execution import open_stream

stream = open_stream(plan, context)
async with stream:
    async for unit in stream:
        print(unit)
```

This is an excerpt: `plan` and `context` are the explicit application-owned
objects constructed in the example. Creating the stream acquires nothing.
Entering it evaluates policy, validates input and acquires dependencies before
the producer body runs. Each iterator pull then runs the producer only until
the next unit. The example records `produce:0`, `consume:0`, `produce:1`,
`consume:1` in that order: there is no prefetch or producer task.

The stream has one owner and one consumption task. Keep entry, iteration and
exit on that task; do not share the stream between consumers. It is one-shot:
create a new stream and invocation context for another consumption. The
container may outlive an individual invocation but remains owned by its loop.

## Completion, abandonment and cleanup

Exhausting the iterator records `StreamTerminal.COMPLETED`. Breaking after the
first unit records `ABANDONED` when the context exits. A `break` does not prove
that the producer completed, even if the last observed value looks final.
Use the context manager around the entire consumption, including early exits.

Context exit closes the producer before releasing its invocation-scoped
dependencies. The event trace ends with `producer.close`, `session.close`.
Closing the application-owned container is a separate responsibility, retained
in `finally` even when stream entry or consumption fails. These local cleanup
fixtures contain no blocking work; arbitrary application teardown can fail or
be interrupted and is not promised a hard termination bound.

## Refusals and partial output

Scope denial raises `PolicyDeniedError` during entry. Malformed direct Python
input raises `ValidationError` there. Neither opens the provider nor enters
the producer. The example catches those specific exceptions for display;
other entry failures propagate after container cleanup.

Once iteration starts, a producer exception or invalid unit raises
`StreamInterrupted`. Inspect its caller-safe `failure`, `units_emitted` and
the stream's terminal state. The example's unexpected failures and invalid
output become `INTERNAL_FAILURE`, with private diagnostics excluded from the
canonical failure. The original exception chain and operator logs are not a
caller-safe response; do not serialize or publish them.

A first-pull producer failure reports zero units. A failure after the first
valid unit leaves that unit delivered and reports one. Output validation
rejects the second invalid value before delivery or incrementing the count.
Do not silently replay a stream after partial output: closing resources does
not undo consumed units or business effects. A yielded `Success` or `Failure`
is also a unit value, not an instruction to bypass its declared schema.

## Caller cancellation and deadlines

`asyncio.CancelledError` propagates; the example does not turn it into a
failure observation. Its `cancelled` mode waits on an event inside the producer.
The [tests](../tests/docs/test_direct_streaming_example.py) start that case
inside a task group, wait for confirmed producer entry, cancel and await the
owning task. They retain the event trace and verify producer closure before
provider closure, container shutdown and no leftover tasks, without sleeps.

The demonstration uses a separate five-second watchdog; its expiry fails the
run and is not a displayed invocation result. To set a real invocation budget,
supply an absolute monotonic `Invocation.deadline`, as described in
[deadlines](DEADLINES.md). A deadline during entry raises `TimeoutError`;
during a pull it raises `StreamInterrupted` with `FailureCode.TIMEOUT` and
records `StreamTerminal.TIMED_OUT`. These deadline paths are covered by the
existing core streaming tests, not demonstrated by this example. Cancellation
and deadlines are cooperative and cannot forcibly interrupt synchronous work.

## Evidence boundary

The tutorial tests check exact lifecycle order and demand, success and early
exit, refusal before effects, redacted partial failure, rejected output,
caller cancellation and execution from outside the checkout. Run:

```bash
uv run pytest tests/docs/test_direct_streaming_example.py tests/architecture
```

This is direct Python consumption evidence. For the separately implemented
HTTP projection, see [HTTP SSE](HTTP_SSE.md). It establishes no MCP streaming,
network backpressure, durable resumption or cross-task stream sharing support.
