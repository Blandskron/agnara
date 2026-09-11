# ADR 0080 — Aborted A5 and A6 Publication Recovery

- Status: Proposed
- Date: 2026-09-08
- Tracking: GitHub Issue #341
- Release: `0.1.0a6`
- Extends: ADR 0078, ADR 0079

## Context

The immutable `v0.1.0a5` tag exercised the publication-readiness control added
after the partial A4 publication. The control found that
`docs/releases/publication.json` was still `UNVERIFIED` and stopped the workflow
before its first upload. PyPI contains no `0.1.0a5` artifact.

The tag is historical and must not be moved, recreated or used for a manual
upload. The release question remains unanswered because the seven-distribution
set has not yet been published and verified complete.

## Decision

`0.1.0a6` is publication recovery and carries the A5 runtime unchanged. It
updates only synchronized package metadata, release records and evidence needed
for a correct publication attempt. Publication remains blocked until the owner
explicitly verifies every PyPI Trusted Publisher for target `0.1.0a6`.

The Execution Semantics horizon defined by ADR 0068 and previously moved by ADR
0078 moves intact to `0.1.0a7`: I2 streaming, I3 execution identity and
idempotency behavior, and I14 performance budgets. Nothing in that scope is
implemented by A6.

```text
0.1.0a4  →  0.1.0a5  →  0.1.0a6  →  0.1.0a7  →  0.1.0b1
 (partial)   (aborted)    recovery    execution    interop
```

## Consequences

- `v0.1.0a5` remains immutable and is documented as aborted, not published.
- A6 retains one thesis: prove complete publication of the reviewed set.
- Publication readiness must continue to fail while owner confirmation is
  absent.
- Execution Semantics loses no scope and does not mix with release recovery.
