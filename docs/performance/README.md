# Performance budgets

`budgets.json` in this directory is the single source of truth for Agnara's
enforced performance limits. `scripts/check_performance_budgets.py` reads it and
fails when a measured value exceeds its limit. CI runs that gate in the
`Performance budgets` job.

`PERFORMANCE.md` at the repository root owns the optimization strategy and the
comparison benchmarks. This directory owns only the enforced limits.

## Why budgets are ratios

Every latency budget is a ratio between two scenarios measured in the same
process, in the same run, within milliseconds of each other.

An absolute nanosecond limit does not survive contact with a shared CI runner.
A loaded machine would fail the gate without any code changing, and the usual
response to that is to widen the limit until it stops complaining, which leaves
a number that no longer detects anything. A ratio moves only when Agnara's own
cost moves relative to the interpreter underneath it.

Feature overhead is budgeted against `compiled_invoke`, a plain compiled
invocation, rather than against a bare `await handler()`. The bare handler costs
about 100ns, close enough to loop and timer overhead that it moved by 2x between
calibration runs; dividing a ~10µs runtime path by it inherits that noise. The
ratio to the bare handler is still recorded, as context for what the framework
costs at all, with a deliberately coarse limit.

Measured across six calibration runs, feature-overhead ratios varied by 1.07x
to 1.42x. The widest spreads belong to the ratios nearest 1.0, where a small
absolute difference is a large relative one. The same measurements expressed
as absolute nanoseconds varied considerably more.

## What is budgeted

| Metric | Protects |
| --- | --- |
| `median_ratio_to_compiled_invoke` | What dependency injection, policy evaluation, execution identity, idempotency, nested invocation and streaming each cost over a plain invocation. |
| `median_ratio_to_reference` | What a compiled invocation costs over a bare awaited handler. Coarse. |
| `startup_scaling_ratio` | Compile cost per capability at 1,000 capabilities over the cost at 100. Catches compilation that stops being linear. |
| `startup_peak_bytes_per_capability` | Peak compile memory. Allocation counts are deterministic across runs, so this limit is tighter than the timing ones. |

Streaming is measured per emitted unit rather than per stream, so it is
comparable with the per-invocation paths.

## Running it

```bash
uv run python scripts/check_performance_budgets.py
```

That runs the benchmarks and checks them. To check a record you already have:

```bash
uv run python benchmarks/runtime_paths.py --json > runtime-paths.json
uv run python scripts/check_performance_budgets.py --record runtime-paths.json
```

## When the gate fails

A budget is a reviewed decision, not a number to adjust until CI is green.

The gate never rewrites `budgets.json`, and nothing else should either. If a
change makes a path genuinely and justifiably more expensive, edit the limit
deliberately in its own commit, move `observed_maximum` to the newly measured
value, and say in the `note` and the pull request why the cost is worth paying.
Widening a limit to clear a red run destroys the only evidence that the limit
was ever meaningful.

## Calibration

Limits were calibrated from six runs of 7 samples x 2,000 iterations with two
warmup batches and the garbage collector disabled during sampling, on CPython
3.14.4, Windows 11, x86-64, 8 CPUs, GIL enabled. Each limit sits at 1.6x the
highest value seen across those runs, which clears the widest spread observed
for any ratio metric.

The first calibration used three runs, and three more runs then exceeded six of
the recorded maxima while staying inside their limits. The recorded values and
the limits were widened to match the larger sample rather than left to look
tighter than the evidence supported. The raw records are in
`docs/benchmarks/data/`.

Every limit carries the `observed_maximum` it was calibrated against; a test
enforces that a budget without calibration evidence, or without headroom over
it, cannot be committed.

The limits are set to catch a regression of roughly 1.6x or worse on a feature
path. They are not a claim that Agnara is fast, a competitor ranking, or a
throughput figure.

## Known limitation

The limits were calibrated on one developer machine and are enforced on
GitHub-hosted runners, which are slower and noisier. The ratio design is what
makes that transfer defensible rather than exact. If the CI lane proves flaky in
practice, the correct response is to widen the specific limit with the runner
measurements recorded as evidence, not to delete the gate.
