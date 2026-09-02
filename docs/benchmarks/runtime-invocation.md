# Runtime Invocation Benchmark

## Purpose

This benchmark measures the warm, transport-neutral execution kernel before
HTTP or another adapter adds decoding, routing, validation, serialization, or
network cost. It supplies a reproducible baseline for E4.9; it is not a claim
that one workstation's latency applies to other Python builds or platforms.

## Compared paths

All scenarios execute the same minimal async handler and return the integer
`42`:

1. `direct_async_handler` awaits the handler directly.
2. `compiled_invoke` uses `agnara.execution.invoke`.
3. `canonical_invoke_result` uses `agnara.execution.invoke_result` and creates
   the protocol-neutral `Success` boundary.

The plan, invocation, execution context, and DI container are constructed once
before timing. The compiled scenarios still include capability identity and
protected-argument checks, telemetry event construction, policy iteration,
the empty DI resolution scope, handler dispatch, awaitable detection, and
terminal event construction. They have no policies, dependencies, telemetry
hooks, or deadline.

Each scenario is warmed independently. The garbage collector is disabled only
during timed samples to reduce collection scheduling noise and is restored
afterward. Correctness is checked after every untimed warmup and timed batch.
The report retains every elapsed sample and summarizes nanoseconds per
operation with minimum, median, mean, maximum, and sample standard deviation.

## Run

From the repository root, after `uv sync`:

```bash
uv run python benchmarks/runtime_invocation.py
uv run python benchmarks/runtime_invocation.py \
  --iterations 100000 --samples 9 --warmups 3 --json
```

The JSON record includes the Git commit and dirty state, CPython version/build,
GIL mode when exposed by the interpreter, OS/platform, processor, CPU count,
timer details, sampling controls, raw samples, summaries, and median ratios to
the direct call.

## Recorded baseline

The initial committed baseline will be recorded after the harness and its JSON
contract pass focused tests. Lower latency is better; no numeric value is a CI
threshold.
