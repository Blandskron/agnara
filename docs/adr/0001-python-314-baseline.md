# ADR 0001 — Python 3.14 Baseline

- Status: Proposed

## Decision

Agnara requires Python 3.14 or newer from its first release.

## Rationale

The project intentionally targets the current generation rather than carrying compatibility constraints from older Python versions.

The architecture must account for free-threaded Python and modern concurrency semantics from the beginning.

## Consequences

Positive:

- simpler compatibility surface;
- modern typing/runtime features;
- explicit free-threading design;
- less legacy branching.

Negative:

- smaller initial user base;
- some third-party integrations may lag Python 3.14/3.14t;
- adapter dependency selection requires care.

## Rule

Do not lower the minimum Python version to increase adoption without a superseding ADR.
