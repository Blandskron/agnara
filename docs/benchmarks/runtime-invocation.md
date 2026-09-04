# Runtime Invocation Benchmark

## Purpose

This benchmark measures the warm, transport-neutral execution kernel before
HTTP or another adapter adds decoding, routing, wire-format conversion,
serialization, or network cost. Core schema validation is included. It
supplies a reproducible baseline for E4.9; it is not a claim that one
workstation's latency applies to other Python builds or platforms.

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
compiled strict input validation, the empty DI resolution scope, handler
dispatch, awaitable detection, and terminal event construction. They have no
policies, dependencies, telemetry hooks, or deadline.

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

The initial baseline was recorded from a clean tree containing the committed
harness:

```text
recorded at: 2026-09-02T20:42:00.796115+00:00
commit: e25fa05639a86b5ca16358e6f47afe9c5f72a46d
dirty: false
command: .venv\Scripts\python.exe benchmarks\runtime_invocation.py --iterations 100000 --samples 9 --warmups 3 --json
platform: Windows 11 10.0.26200 (AMD64)
processor: Intel64 Family 6 Model 140 Stepping 1, GenuineIntel
logical CPU count: 8
Python: CPython 3.14.4 (tags/v3.14.4:23116f9, Apr 7 2026 14:10:54)
GIL enabled: true
timer: QueryPerformanceCounter(), 100 ns reported resolution
workload: one task, sequential warm invocations, integer payload {"value": 41}
server / workers / serializer / concurrency: not applicable to this in-process benchmark
```

| Scenario | Minimum ns/op | Median ns/op | Mean ns/op | Maximum ns/op | Sample stdev ns/op | Median/direct |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct async handler | 87.298 | 107.047 | 102.871 | 120.614 | 12.679 | 1.00x |
| Compiled `invoke` | 5,623.986 | 6,953.200 | 6,792.540 | 7,752.341 | 583.275 | 64.95x |
| Canonical `invoke_result` | 7,263.325 | 7,711.570 | 7,693.491 | 7,934.519 | 224.467 | 72.04x |

The median absolute overhead relative to the direct async call on this one run
was approximately 6.85 microseconds for `invoke` and 7.60 microseconds for
`invoke_result`. These values characterize the current reference implementation
on the recorded conventional-GIL Windows build. They are not a cross-platform
claim, competitor comparison, regression threshold, or proof that any specific
runtime component is the bottleneck. Profiling and repeated measurements on
representative deployment builds must precede optimization.

## Input-validation checkpoint

Issue #111 added one precompiled strict `int` schema check to the measured
compiled paths. Two consecutive dirty-tree checkpoint runs used the same
command, source state, machine, interpreter, and sampling controls as the
initial baseline. Recording both is intentional: the fixed-order scenarios
showed substantial workstation frequency/scheduling variance, so selecting
only the more favorable run would overstate precision.

```text
source base commit: 86443bdcfc3f362505ac97470220f85a0f13db84
dirty: true (Issue #111 implementation under measurement)
recorded at: 2026-09-02T21:23:00.252289+00:00 and 2026-09-02T21:23:41.060965+00:00
command: .venv\Scripts\python.exe benchmarks\runtime_invocation.py --iterations 100000 --samples 9 --warmups 3 --json
```

| Scenario | First median ns/op | Second median ns/op | Observed median range |
| --- | ---: | ---: | ---: |
| Direct async handler | 88.287 | 90.201 | 88.287–90.201 |
| Compiled `invoke` | 11,040.347 | 6,807.125 | 6,807.125–11,040.347 |
| Canonical `invoke_result` | 12,278.055 | 11,789.887 | 11,789.887–12,278.055 |

The `invoke` checkpoint range straddles the original 6,953.200 ns/op median,
while both canonical checkpoint medians exceed the original 7,711.570 ns/op
median. Because the scenarios run in fixed batches and the two immediate runs
disagree materially for `invoke`, this evidence confirms that validation is
present in the measured hot path but does not isolate its cost reliably. A
future optimization claim should first add interleaved or externally controlled
benchmarking and repeat measurements on representative deployment systems.
