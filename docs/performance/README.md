# Performance budgets

`budgets.json` in this directory is the single source of truth for Agnara's
enforced performance limits. `scripts/check_performance_budgets.py` reads it and
fails when a measured value exceeds its limit. CI runs that gate in the
`Performance budgets` job.

The file is schema version 2. The checker refuses another version, unknown
budget metric names, an unsupported record schema, duplicate or unbudgeted
benchmark records, and any enforceable recorded metric without a budget. It
also verifies the declared CPython/Python/GIL execution profile and every
semantic execution dimension before comparing values. A typo, incomplete
artifact, or result from a different benchmark contract therefore cannot
silently become an unenforced pass. Adding a metric requires an intentional
checker, test, calibration-record and reviewed-budget change.

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

Three checked-in schema-2 calibration records establish the current limits.
They include declared environment and semantic dimensions for the embedding,
registration/freeze and invocation paths. Absolute nanoseconds vary more
across machines, so the ratios and reviewed headroom are the enforced signal.

## What is budgeted

| Metric | Protects |
| --- | --- |
| `median_ratio_to_compiled_invoke` | What dependency injection, policy evaluation, execution identity, idempotency, nested invocation and streaming each cost over a plain invocation. |
| `median_ratio_to_reference` | What a compiled invocation costs over a bare awaited handler. Coarse. |
| `startup_scaling_ratio` | Compile cost per capability at 1,000 capabilities over the cost at 100. Catches compilation that stops being linear. |
| `startup_peak_bytes_per_capability` | Peak compile memory. Allocation counts are deterministic across runs, so this limit is tighter than the timing ones. |

The currently enforced streaming measure is per emitted unit over a complete
lifecycle. The benchmark also records opening, per-item pull and normal completion as
separate observations. Registration/freeze and the ADR 0094 embedding boundary
are likewise observed where no reviewed threshold exists. See
`docs/benchmarks/coverage.md`.

## Running it

```bash
uv run python scripts/check_performance_budgets.py
```

That runs the benchmarks and checks them. To check a record you already have:

```bash
uv run python benchmarks/runtime_paths.py --json > runtime-paths.json
uv run python scripts/check_performance_budgets.py --record runtime-paths.json
```

The `Performance budgets` CI job first runs the deterministic synthetic
fail/pass proof in `tests/benchmarks/test_performance_budget_gate.py`. That
proof drives this same command-line checker with an over-budget artifact and
asserts a non-zero exit, then validates an in-budget artifact. The job then
records the real JSON artifact and runs the local command above against it.

## When the gate fails

A budget is a reviewed decision, not a number to adjust until CI is green.

The gate never rewrites `budgets.json`, and nothing else should either. If a
change makes a path genuinely and justifiably more expensive, edit the limit
deliberately in its own commit, move `observed_maximum` to the newly measured
value, and say in the `note` and the pull request why the cost is worth paying.
Widening a limit to clear a red run destroys the only evidence that the limit
was ever meaningful.

## Calibration

The preserved calibration is three runs of 7 samples x 2,000 iterations with
two warmup batches and the garbage collector disabled during sampling, on
CPython 3.14.4, Windows 11, x86-64, 8 CPUs, GIL enabled. Each existing limit
sits at 1.6x the highest recorded value. The raw records are in
`docs/benchmarks/data/`.

The three raw JSON records in `docs/benchmarks/data/` retain their full
execution profile and metric dimensions. Budgets were set from the maximum
observed value with reviewed headroom; no historical task identifier is needed
to interpret the current gate.

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
