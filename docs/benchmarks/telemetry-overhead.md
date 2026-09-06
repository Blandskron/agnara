# Telemetry Overhead Benchmark

## Purpose

E9.1 through E9.5 each declined to make a performance claim and deferred the
evidence to E9.6. This benchmark answers one question: what does an application
pay for the telemetry port, separated into what the port costs, what having any
observer costs, and what each OpenTelemetry adapter costs.

It supplies a reproducible baseline for E9.6. It is not a claim that one
workstation's latency applies to other Python builds or platforms, and it is
not a CI threshold.

## Compared configurations

Every scenario invokes the same compiled plan over the same minimal async
handler returning `42`. Only the registered hooks differ:

1. `no_hooks` — the baseline, and what most applications run.
2. `one_noop_hook` — a hook that is registered, validated and delivered to,
   and does nothing. This separates the cost of *having* an observer from the
   cost of what an observer does.
3. `four_noop_hooks` — the same, four times, for per-hook scaling.
4. `otel_metrics_hook` — the real `OpenTelemetryMetricsHook`.
5. `otel_tracing_hook` — the real `OpenTelemetryTracingHook`.
6. `otel_metrics_and_tracing` — both on one plan.

The plan, invocation, execution context and DI container are constructed once
before timing. Exporters are in-memory: this measures hook work, never network,
batching or serialization cost, so the adapter numbers are a floor rather than
a production figure.

Each scenario is warmed independently. The garbage collector is disabled only
during timed samples and restored afterward. Correctness is checked after every
untimed warmup and every timed batch. The JSON record retains every elapsed
sample.

## Run

From the repository root, after `uv sync`:

```bash
uv run python benchmarks/telemetry_overhead.py
uv run python benchmarks/telemetry_overhead.py \
  --iterations 50000 --samples 9 --warmups 3 --json
```

Unlike `runtime_invocation.py`, this benchmark imports the pinned development
OpenTelemetry SDK, because measuring the adapters is half the point.

## Recorded baseline

CPython 3.14.4, GIL enabled, Windows 11 (10.0.26200), Intel64 Family 6 Model
140 Stepping 1, 8 logical CPUs, `QueryPerformanceCounter()` at 1e-07 s
resolution. 9 samples x 20,000 iterations, 3 warmups. Recorded 2026-09-05.

| Scenario | min ns/op | median ns/op | stdev | over baseline |
| --- | ---: | ---: | ---: | ---: |
| `no_hooks` | 4,268 | 4,404 | 100 | — |
| `one_noop_hook` | 8,294 | 8,892 | 772 | +4,488 |
| `four_noop_hooks` | 11,062 | 11,794 | 622 | +7,390 |
| `otel_metrics_hook` | 17,934 | 20,266 | 1,328 | +15,863 |
| `otel_tracing_hook` | 40,211 | 41,282 | 3,053 | +36,878 |
| `otel_metrics_and_tracing` | 59,267 | 68,602 | 9,128 | +64,198 |

Read the adapter rows as an ordering, not as absolute costs: the stdev on the
combined row is 13% of its own median, and in-memory exporters understate a
real pipeline.

## What the measurement changed

The first run of this benchmark was taken against a runtime that built both
lifecycle events on every invocation, whether or not any hook was registered.
Measured in isolation on the same machine, that unconditional work was:

```text
uuid4().hex            1,009.6 ns
start event              361.2 ns
terminal event           504.2 ns
combined               2,177.5 ns
```

An application with no hooks paid all of it and could observe none of it,
because there was no hook to deliver the events to. `invoke` now skips
identity generation, tracking-ID resolution, clock reads and event
construction when `plan.hooks` is empty. PERFORMANCE.md puts "eliminate
unnecessary work" first; the benchmark came before the change, as AGENTS.md
requires. Recorded by ADR 0058.

## A/B evidence, and its limits

The change was measured with four order-balanced rounds. Rounds 1 and 3 ran
the unguarded build first, rounds 2 and 4 ran the guarded build first, because
a first attempt with a fixed order produced results confounded by machine
drift. Minimum ns/op per round, guarded minus unguarded:

| Scenario | R1 | R2 | R3 | R4 |
| --- | ---: | ---: | ---: | ---: |
| `no_hooks` | -2,909 | -4,363 | -3,295 | -4,323 |
| `one_noop_hook` | +3,495 | +887 | +2,810 | +1,273 |
| `four_noop_hooks` | +1,960 | +313 | -2,700 | +127 |
| `otel_metrics_hook` | +2,653 | -1,835 | +245 | -5,322 |
| `otel_tracing_hook` | +6,610 | -4,497 | +2,955 | +6,206 |
| `otel_metrics_and_tracing` | +4,345 | -4,173 | +169 | -3,560 |

**What this supports.** `no_hooks` is faster in every round, by roughly 2.9 to
4.4 microseconds. The direction is consistent, the magnitude is the same order
as the isolated component measurement above, and the mechanism is known.

**What this does not support.** Any claim about the hooked rows, in either
direction. Their per-round deltas swing by up to 11 microseconds and change
sign, which is larger than any effect three truthiness checks could produce.
The `one_noop_hook` row is positive in all four rounds, and that is reported
rather than explained: the code change cannot account for a microsecond-scale
regression there, so it is most likely an artefact of this machine, but this
benchmark cannot prove that. A quieter machine would be needed to say more.

Correctness, unlike performance, is not left to a benchmark:
`tests/unit/execution/test_unobserved_invocation.py` asserts that no identity,
tracking ID or clock read happens without hooks, that exactly one identity is
generated with them, and that every outcome still delivers an unchanged event
pair.

## Limits

One workstation, one interpreter build, GIL enabled. No portable ranking, no
throughput claim, no free-threading claim, no CI threshold, and no comparison
against another framework's telemetry. In-memory exporters mean the adapter
rows exclude everything a production pipeline adds.
