# ADR 0073 — Reviewed Distribution Publication Set

- Status: Accepted
- Date: 2026-09-11
- Release target: `1.0.0`

## Context

Agnara is a synchronized set of first-party distributions. Publishing only a
subset can leave users with adapter metadata that resolves to an incompatible
core or with a missing documented package.

## Decision

The `1.0.0` release gate reviews and publishes the complete first-party
distribution set together. The set, expected versions, registry state and
verification evidence are recorded in `docs/releases/publication.json`; the
workflow validates that record before it publishes.

The retained A8 publication demonstrates the workflow baseline. It is not a
template for partial release attempts. A failed publication is handled through
an Issue and a reviewed correction, never by silently reusing a version or
retagging a different commit.

## Consequences

Release preparation is broader than building one wheel, but it gives users a
single documented compatibility point. Future independent package cadence
requires a separate ADR with a compatibility and registry strategy.
