# ADR 0058 — An Unobserved Invocation Builds No Telemetry

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #227 (E9.6)

## Context

ADR 0023 made lifecycle events unconditional: `invoke` built an
`InvocationStartEvent` before execution and an `InvocationTerminalEvent` in its
`finally`, then iterated `plan.hooks`. When that tuple is empty the events are
constructed, never delivered, and immediately discarded.

E9.3 added a `uuid4().hex` per invocation to that unconditional path, and the
E9.5 work left the question of what any of it costs still open. Every ADR in
EPIC 9 declined to make a performance claim and deferred the evidence to E9.6.

Measured in isolation on the maintainer workstation:

```text
uuid4().hex            1,009.6 ns
start event              361.2 ns
terminal event           504.2 ns
combined               2,177.5 ns
```

An application that has not opted into telemetry — the default — paid all of
it and could observe none of it.

## Decision

`invoke` performs observer-only work only when `plan.hooks` is non-empty.
Identity generation, tracking-ID resolution, both clock reads and both event
constructions are guarded.

`plan.hooks` is a frozen tuple fixed at compilation, so the guard is a
truthiness check on an immutable attribute, not a cache that could go stale. A
plan with hooks is unaffected in every observable way: the same events, with
the same fields, delivered to the same hooks in the same order, for every
outcome.

The benchmark preceded the change. PERFORMANCE.md puts "eliminate unnecessary
work" first in its optimization order and AGENTS.md forbids optimizing by
guess, so `benchmarks/telemetry_overhead.py` was written and run first, and the
change is justified by its output rather than by the shape of the code.

## Evidence, and what it does not show

Four order-balanced A/B rounds — rounds 1 and 3 ran the unguarded build first,
rounds 2 and 4 ran the guarded build first, because a first attempt with a
fixed order produced results confounded by machine drift.

`no_hooks` was faster in every round, by roughly 2.9 to 4.4 microseconds. The
direction is consistent across rounds, the magnitude is the same order as the
isolated component measurement, and the mechanism is known.

Nothing is claimed about the hooked scenarios. Their per-round deltas swing by
up to 11 microseconds and change sign, which is far larger than three
truthiness checks could produce. One of them, `one_noop_hook`, was positive in
all four rounds; that is reported in `docs/benchmarks/telemetry-overhead.md`
rather than explained away, because this machine cannot distinguish a real
microsecond-scale regression from its own noise, and the code change cannot
account for one.

Correctness is not left to a benchmark.
`tests/unit/execution/test_unobserved_invocation.py` asserts that without hooks
no identity is generated, no tracking ID is resolved and no clock is read; that
with a hook exactly one identity is generated; that all four outcomes still
deliver an unchanged event pair; and that an unobserved plan cannot silence an
observed one. Reverting the guard fails three of those.

## Consequences

Telemetry is now something an application pays for when it uses it, rather than
a fixed cost of the runtime. That is the point, and it also removes the
argument for making the hook list mutable or lazily built later.

A profiler will no longer show `uuid4` on the invocation path of an
application without hooks. Anyone who was using that as evidence the telemetry
port exists should look at `plan.hooks` instead.

The guard is three conditional expressions and one `if`, which AGENTS.md's
requirement that an optimization preserve a readable reference design permits.
A more aggressive version — compiling two variants of `invoke` at plan
compilation — would be faster still and would fork the runtime's most
security-sensitive function. Rejected on those grounds, not on measurement.

`duration_ns` is still measured across the whole guarded region when hooks
exist, so no observed measurement changed meaning. Without hooks there is no
duration to report and the clock is not read at all.

## Alternatives considered

**Leave it unconditional.** Simplest, and defensible if the cost were noise.
It is not: it was the single largest avoidable component on the unobserved
path, and it grew when E9.3 added an identity.

**Make the identity lazy.** A deferred object that generates on first access
would keep the code shape and skip the cost when nothing reads it. It replaces
a plain string in a frozen public event with a proxy, which is worse for every
observer in order to avoid one branch.

**Compile two `invoke` variants.** Rejected above: forking the function that
enforces policy order and input validation to save a branch is not a trade this
project should make.

## Scope

No policy, ordering, validation or public API change. No free-threading claim,
no cross-platform claim, no throughput claim and no CI performance threshold.
The adapter rows in the recorded baseline use in-memory exporters and are a
floor, not a production figure.

Proposed status does not claim maintainer architectural approval.

## Evidence index

- `benchmarks/telemetry_overhead.py` — six hook configurations, standard
  sampling harness, JSON record with environment and Git metadata.
- `docs/benchmarks/telemetry-overhead.md` — recorded baseline, the A/B table
  and its limits.
- `tests/unit/execution/test_unobserved_invocation.py` — 12 correctness cases,
  three of which fail if the guard is removed.
