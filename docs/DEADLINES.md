# Direct invocation deadlines and cancellation

Run the complete example from a synchronized development checkout:

```bash
uv sync
uv run python examples/deadlines.py
```

[examples/deadlines.py](../examples/deadlines.py) uses governed public imports,
one compiled execution plan and an explicitly owned DI container. Its principal
is a trusted local fixture, not an authentication implementation. No network,
database or business data is changed.

The first four output lines are:

```text
success: done
denied: forbidden
timeout: timeout
cancelled: CancelledError
```

The final event list contains three repetitions of `session.open`,
`handler.enter`, `handler.exit`, `session.close`: one for success, one for the
expired deadline and one for caller cancellation. The scope-denied call adds
no events.

## Supply an absolute monotonic deadline

`Invocation.deadline` is a finite absolute timestamp in the running event
loop's monotonic clock. Compute a duration budget at the composition boundary:

```python
import asyncio

from agnara.execution import ExecutionContext, Invocation, invoke_result

deadline = asyncio.get_running_loop().time() + 30
invocation = Invocation(plan.definition.id, {"wait": True}, {}, deadline=deadline)
context = ExecutionContext(invocation, container, principal=actor)
outcome = await invoke_result(plan, context)
```

Here `plan`, `container` and `actor` are the explicit application-owned objects
from the example. A value of `30` alone is not a thirty-second timeout. Wall
clock timestamps from `time.time()` or calendar dates use the wrong clock.
`None` means no invocation deadline. `context.remaining_time()` reports the
remaining duration clamped to zero, or `None` without a deadline; reading it
does not enforce a timeout.

The runtime wraps policy evaluation, input binding, dependency construction
and handler execution in the invocation deadline. `invoke_result` returns a
canonical `Failure` with `FailureCode.TIMEOUT` when execution raises
`TimeoutError`; the lower-level `invoke` boundary raises the exception instead.
A handler's own `TimeoutError` uses the same canonical category, so this result
alone does not identify which boundary exhausted its budget.

## Cancellation belongs to the caller

The example starts the invocation inside an `asyncio.TaskGroup`, waits for an
event proving handler entry, then cancels and awaits the task. It catches
`asyncio.CancelledError` only at that caller boundary so it can print the
demonstrated outcome. `invoke_result` propagates cancellation; it does not
return a canonical failure for it. The example also re-raises cancellation of
its own caller, including the watchdog's cancellation. In ordinary application
code, propagate cancellation after any caller-owned cleanup unless that boundary
deliberately owns and handles the cancellation.

The task group owns and joins the work. There is no fire-and-forget invocation,
and the handler blocks on an event rather than a timing sleep. A separate
five-second `asyncio.timeout` watchdog bounds the demonstration. Its expiry
would fail the run; it is not one of the displayed invocation results.

## Cleanup is owned and cooperative

The explicit `Scope.INVOCATION` async-generator provider yields a `Session`
fixture and releases it in `finally`. The invocation exits the handler before
closing its dependency scope, including on timeout and cancellation. The
composition root closes the application container in its own `finally` with
`await container.aclose()`. Container shutdown also owns singleton teardown
when singleton providers are configured; this example uses only invocation
resources.

Deadlines use cooperative asyncio cancellation. Synchronous handlers and
providers run inline and can block the event loop; a deadline cannot forcibly
interrupt them. Even an already-expired direct invocation can acquire a
resource and enter the handler before its first suspension. The example
deliberately demonstrates that behavior with `loop.time() - 1`, avoiding a
race over a short positive timeout. A deadline is not authorization or an
assurance that no work began.

The teardown fixture awaits an already-set event, so cleanup needs no timing
delay. Real cleanup can take additional time, raise, or be interrupted by
further cancellation. Neither deadlines nor this example promise a hard
wall-clock termination bound for arbitrary application code. Releasing a
resource does not roll back completed business effects; transactions,
idempotency and recovery require explicit application design.

## Evidence and limits

[The guide tests](../tests/docs/test_deadlines_example.py) check canonical
outcomes, propagated cancellation, exact resource lifecycle order, no effects
for scope denial, container shutdown, no leftover tasks and execution from
outside the checkout. Existing execution tests cover the underlying deadline
and cancellation contracts. These are direct invocation checks on the current
Python baseline, not HTTP/MCP timeout, streaming, distributed cancellation or
free-threading evidence.

For related ownership boundaries, see [nested invocation](NESTED_INVOCATION.md)
and [HTTP SSE lifecycle](HTTP_SSE.md). No new API or dependency is introduced.
