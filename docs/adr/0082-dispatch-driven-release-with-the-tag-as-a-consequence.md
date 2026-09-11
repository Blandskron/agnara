# ADR 0082 — Dispatch-Driven Publication

- Status: Accepted
- Baseline: `0.1.0a8`

## Decision

Publication is a reviewed `workflow_dispatch` operation from `main`. The
workflow runs quality, build, installation and registry-verification gates
before waiting for approval in the protected publishing environment. Only the
approved final operation creates a tag and GitHub Release.

The workflow builds and verifies the complete synchronized distribution set.
It records registry configuration separately from per-release authorization,
and it never turns a failed or incomplete publication into a tag.

## Consequences

`0.1.0a8` is the retained evidence that this publication path works. Future
publication, including `1.0.0`, uses this path and must not recreate a
pre-gate tagging flow.
