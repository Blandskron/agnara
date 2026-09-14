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

The historical preview surface was experimental, and its
public API may change without a deprecation cycle. Calling selected Python
objects stable merely because their semantic identity is described as stable
would contradict that release scope.

## Decision

`docs/public-api.json` is the machine-readable inventory for the top-level
`agnara` module. It records each export exactly once, in `__all__` order, with
one of `stable`, `provisional`, `experimental` or `internal`.

The 41 current exports are `provisional`. They are intentional public entry
points, but none receives a stable compatibility promise before `1.0.0`.
Internal names do not belong in `__all__` or the manifest; the `internal`
classification is defined so reviews share one vocabulary, not to legitimize
an accidental export.

`docs/PUBLIC_API.md` owns the human-facing classification and change policy.
The automated release gate parses the implementation's literal `__all__` and
requires its ordered names to equal the manifest. It also validates the
manifest schema, unique names and classification vocabulary.

This decision first governed only `agnara.__all__`. Subpackage entry points
remained public and were inventoried in the follow-up recorded below, without
blocking the first exact contract on a larger audit.

## Consequences

- Adding, removing, renaming or reordering a top-level export fails the release
  gate until its classification is reviewed.
- Snapshot changes are visible but do not prove compatibility or promote an
  API to stable.
- Pre-1.0 incompatible changes retain ADR 0021's changelog and migration
  requirements.
- I9 remains open for eventual stability promotion.

## Alternatives considered

**Keep checking only the number 41.** Rejected because a rename preserves the
count while breaking every importing application.

**Treat every provisional export as experimental.** Rejected because these are the
deliberate framework entry points, not disposable spikes. `provisional`
records intent without fabricating a stable guarantee.

**Classify every public submodule in one change.** Rejected because it turns a
cheap guardrail into a broad compatibility audit. Exact top-level governance
can ship independently and makes the remaining scope measurable.

**Store stability on runtime objects.** Rejected because compatibility
classification is release metadata, not invocation semantics, and core should
not carry mutable governance machinery at runtime.

## Follow-up — subpackage manifests (Issue #275)

The manifest carries one classified export list per public module and uses
`schema_version` 2. It governs `agnara`, `agnara.capability`, `agnara.core.di`,
`agnara.execution`, `agnara.introspection`, `agnara.policy` and `agnara.schema`
— 123 exports, all `provisional`.

The alternative "classify every public submodule in one change" was rejected
above for the *first* contract, and that reasoning held: the top-level gate
shipped independently and made the remaining scope measurable. This follow-up
is that measured scope, not a reversal.

Two things were deliberately left alone. Nothing is renamed or re-exported: in
particular, whether `agnara.core.di` is the right public spelling for
dependency injection is a design question, and `core` appearing in the first
import of the README is a real one — but a rename does not belong inside a
governance change that exists to make the current surface visible. And nothing
is promoted to `stable`, which still requires the `1.0.0`
gates.
