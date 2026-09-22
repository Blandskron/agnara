# Runtime Paths Benchmark

## Purpose

`runtime-invocation.md` covers the bare compiled hot path. This benchmark covers
what the 1.0.0 performance program has to protect: what a capability pays for
dependency injection, policy evaluation, execution identity, idempotency, nested
composition, framework-neutral embedding and streaming, plus distinct
registration/freeze and compile/startup scaling and memory.

It is the measurement behind `docs/performance/budgets.json`. It is not a claim
that one workstation's latency applies elsewhere, a competitor ranking, or a
throughput figure.

## Compared paths

Every complete-result scenario executes the same minimal async handler and
returns `42`.

| Scenario | What it adds over `compiled_invoke` |
| --- | --- |
| `direct_async_handler` | Nothing; a bare awaited handler, for context only. |
| `compiled_invoke` | The baseline every feature ratio is measured against. |
| `dependency_injection_one` | One invocation-scoped dependency. |
| `dependency_injection_ten` | Ten invocation-scoped dependencies. |
| `policy_evaluation_one` | One always-allow policy. |
| `policy_evaluation_three` | Three always-allow policies. |
| `execution_identity` | A principal and a per-invocation correlation id. |
| `idempotency_miss` | A fresh claim plus complete against the store. |
| `idempotency_hit` | Replay of one stored result. |
| `nested_depth_one` | One nested capability invocation through the runtime. |
| `nested_depth_three` | A three-level nested chain. |
| `embedded_runtime_invoke` | One ADR 0094 host-to-runtime `invoke_result` call through a frozen registry. |
| `stream_open` | The pre-output opening phase only; setup and close are outside the timer. |
| `stream_per_item` | One consumer pull from an already-open stream. |
| `stream_completion` | The normal terminal pull after a stream was drained. |
| `streaming_unit` | Per emitted unit of a 16-unit stream. |

The policies deliberately allow: a denying policy short-circuits and would
measure less work, not more. The dependencies are deliberately trivial to
construct, because the measurement is what the DI boundary costs, not what a
user's provider costs.

Unlike `runtime_invocation.py`, the execution context is constructed per
invocation rather than reused, because that is what a real caller does.

The three phase measurements are observations, not ratios: their preparation
and cleanup are intentionally outside the timer so each measures its real
operation rather than a full lifecycle. `streaming_unit` retains the complete
lifecycle divided by units and is the calibrated, comparable release metric.
The JSON record is schema version 2; version 1 consumers must not assume that
the added observations are comparable release ratios.

## Startup

Registration/freeze and plan compilation are each measured for 100 and 1,000
capabilities. Compile cost is reported as
nanoseconds and peak bytes per capability. The enforced signal is
`startup_scaling_ratio`, the per-capability cost at 1,000 divided by the cost at
100, which catches compilation that stops being linear in the number of
capabilities without asserting a wall-clock number.

Peak memory is captured with `tracemalloc` over a retained compile, so it
reflects what the compiled snapshot holds rather than transient garbage.

## Method

Each scenario is warmed independently, then sampled with the garbage collector
disabled during timed samples and restored afterwards. Correctness is checked
after every untimed warmup and every timed batch, so a scenario cannot get fast
by doing the wrong thing. Every elapsed sample is retained alongside the summary.

## Calibration record

The checked-in calibration is three runs of 7 samples x 2,000 iterations and
2 warmup batches on CPython 3.14.4, Windows 11, x86-64, 8 CPUs, GIL enabled.
It predates the final-semantics observations above.  V1-40 must create a new,
repeated calibration set before setting limits for them. Nanoseconds per
operation, lower is better.

| Scenario | ns/op | x `compiled_invoke` | x bare handler |
| --- | ---: | ---: | ---: |
| `direct_async_handler` | 84 | — | — |
| `compiled_invoke` | 10,554 | — | 125.5 |
| `policy_evaluation_one` | 10,686 | 1.01 | 127.1 |
| `execution_identity` | 10,818 | 1.03 | 128.6 |
| `policy_evaluation_three` | 11,633 | 1.10 | 138.3 |
| `dependency_injection_one` | 16,926 | 1.60 | 201.3 |
| `dependency_injection_ten` | 24,244 | 2.30 | 288.3 |
| `idempotency_hit` | 20,208 | 1.91 | 240.3 |
| `idempotency_miss` | 38,028 | 3.60 | 452.2 |
| `nested_depth_one` | 45,534 | 4.31 | 541.4 |
| `nested_depth_three` | 98,446 | 9.33 | 1170.6 |
| `streaming_unit` (per unit) | 2,950 | 0.28 | 35.1 |

Startup: 2,695 peak bytes per capability at 100 capabilities and 2,357 at 1,000,
identical in every preserved run; scaling ratio 0.78-1.61 across three runs.

The raw records for all three preserved calibration runs are in `docs/benchmarks/data/`,
and `docs/performance/budgets.json` cites the maximum of each metric across
them as the value its limit was calibrated against.

## What the numbers say

Policy evaluation and execution identity are close to free. Ten dependencies
cost about 2.3x a plain invocation rather than ten times one dependency, so the
DI boundary has a fixed component rather than a purely per-dependency one.
Nested depth three costs about 2.2x nested depth one, which is close to linear
in depth.

## Regression that this benchmark found

`idempotency_miss` originally measured 174µs at 2,000 iterations against 37µs at
50, which is the signature of quadratic behaviour rather than noise.
`InMemoryIdempotencyStore._discard_expired` swept and copied every stored record
on every `claim`, `lookup`, `complete` and `abandon`. Measured directly, one
claim plus complete cost 18.9µs against an empty store and 473µs against 4,000
records, growing linearly per operation and therefore quadratically overall.

Expiry is now resolved for the record being touched, and the full sweep runs only
when capacity is actually exhausted. The same measurement is flat at about 9µs
from 0 to 4,000 records, and a single operation is about 2x cheaper even on an
empty store because `complete` no longer sweeps.

`tests/unit/execution/test_idempotency.py` pins this by counting full
traversals rather than by asserting a wall-clock number, so it cannot fail on a
loaded machine.

## Run

From the repository root, after `uv sync`:

```bash
uv run python benchmarks/runtime_paths.py
uv run python benchmarks/runtime_paths.py --json > runtime-paths.json
```

Enforce the budgets:

```bash
uv run python scripts/check_performance_budgets.py
```
