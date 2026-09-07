# ADR 0067 — Explicit Public API Stability

- Status: Proposed
- Date: 2026-09-06
- Initiative: I9 Public API governance
- Tracking: GitHub Issue #270

## Context

The `agnara` module exports 41 names. `docs/MATURITY.md` checks only that count,
and the release-readiness gate checks only that each distribution contains the
text `__all__`. Replacing one export with another leaves both checks green.
Nothing classifies an individual name, so every export is an implicit and
ambiguous compatibility commitment.

The repository is also explicit that `0.1.0a3` is experimental alpha and its
public API may change without a deprecation cycle. Calling selected Python
objects stable merely because their semantic identity is described as stable
would contradict that release scope.

## Decision

`docs/public-api.json` is the machine-readable inventory for the top-level
`agnara` module. It records each export exactly once, in `__all__` order, with
one of `stable`, `provisional`, `experimental` or `internal`.

The 41 current exports are `provisional`. They are intentional public entry
points, but none receives a stable compatibility promise during alpha.
Internal names do not belong in `__all__` or the manifest; the `internal`
classification is defined so reviews share one vocabulary, not to legitimize
an accidental export.

`docs/PUBLIC_API.md` owns the human-facing classification and change policy.
The automated release gate parses the implementation's literal `__all__` and
requires its ordered names to equal the manifest. It also validates the
manifest schema, unique names and classification vocabulary.

This decision governs only `agnara.__all__`. Subpackage entry points remain
public; follow-up work will inventory them without blocking this first exact
contract on a larger audit.

## Consequences

- Adding, removing, renaming or reordering a top-level export fails the release
  gate until its classification is reviewed.
- Snapshot changes are visible but do not prove compatibility or promote an
  API to stable.
- Pre-1.0 incompatible changes retain ADR 0021's changelog and migration
  requirements.
- I9 remains open for subpackage manifests and eventual stability promotion.

## Alternatives considered

**Keep checking only the number 41.** Rejected because a rename preserves the
count while breaking every importing application.

**Treat every alpha export as experimental.** Rejected because these are the
deliberate framework entry points, not disposable spikes. `provisional`
records intent without fabricating a stable guarantee.

**Classify every public submodule in one change.** Rejected because it turns a
cheap guardrail into a broad compatibility audit. Exact top-level governance
can ship independently and makes the remaining scope measurable.

**Store stability on runtime objects.** Rejected because compatibility
classification is release metadata, not invocation semantics, and core should
not carry mutable governance machinery at runtime.
