# ADR 0076 — Workspace-Wide Public API Governance

- Status: Proposed
- Date: 2026-09-07
- Initiative: I9 Public API governance
- Supersedes the manifest schema of ADR 0067 and ADR 0074

## Context

The baseline asks one question: can Agnara be consumed as a framework from outside
this repository? An application that answers yes imports `agnara_http` and
`agnara_mcp` as readily as `agnara`.

Governance did not follow that shape. ADR 0067 and ADR 0074 classified the core
distribution exactly — 218 exports across 30 modules, checked in both
directions by the release gate — and stopped there. `docs/public-api.json`
declared `"distribution": "agnara"` in its schema, so the adapters could not be
described by it even in principle. The audit of `develop` at `462b002` found:

- `agnara-mcp` publishing 40 export slots across nine public modules with no
  classification of any kind;
- `agnara-telemetry` publishing four across three, likewise;
- `agnara-cli` publishing 17 names, thirteen of them re-exported from
  underscore-prefixed modules, none documented, none used anywhere in the
  workspace, none designed as an API;
- `agnara-http` governed by a hand-written tuple in one architecture test
  rather than by the manifest, so the mechanism that governed the kernel and
  the mechanism that governed the adapter were different mechanisms;
- `agnara-a2a` and `agnara-events` declaring `__all__ = []`, which the reverse
  walk skips, leaving the reserved namespaces the one place a first export
  could appear ungoverned.

`docs/MATURITY.md` counted each distribution's entry-point exports, but a count
survives a rename, which is exactly the reasoning ADR 0067 used to reject
counting for the core.

Separately, `docs/INITIATIVES.md` recorded I9 as `PLANNED` while its own body
described shipped, enforced machinery.

## Decision

**One manifest governs the whole workspace.** `docs/public-api.json` moves to
`schema_version` 3 and carries a `distributions` list. Each entry names the
distribution, its import root, and the exact ordered export list of every
public module it ships. All seven distributions are present; a missing one
fails the gate.

**The boundary rule does not change.** A non-private module with a non-empty
literal `__all__` is public and must be classified. The rule now applies to
every distribution's source root rather than the core's.

**A reserved namespace classifies its empty surface.** `agnara_a2a` and
`agnara_events` appear in the manifest with zero exports, so gaining a first
export fails the ordered comparison. The reverse walk continues to ignore empty
`__all__` declarations, which is why the explicit entry is needed.

**A manifest entry may not reach sideways.** A module is resolved against the
source root of the distribution that claims it, and a distribution may not
classify another's module.

**`agnara-cli` publishes four names.** `EXIT_OK`, `EXIT_FAILED`, `EXIT_USAGE`
and `main` are what a caller needs to run the `agnara` command in-process. The
thirteen manifest-parsing, generation-planning and target-resolution names are
removed from `__all__`. They remain importable from the private modules that
define them, which is an accurate statement of what they are.

**Public-only consumption is decided mechanically, on any tree.**
`scripts/check_public_imports.py` reads the manifest and reports every import
that names an unclassified module or pulls an unclassified name out of a
classified one, in Python files and in the Python shown in Markdown fences. It
takes arbitrary paths so that an application built outside this workspace is
audited by the same rule as `examples/`.

**The rule is enforced where an application would copy from, and exempt where
history is recorded.** `examples/`, `README.md`, the guides under `docs/` and
the CLI's generated projects must import governed names only. `docs/adr/` and
`docs/rfc/` are exempt because a decision record may quote a rejected or
superseded spelling — RFC 0001 sketches `from agnara import Agnara, Context`,
an API that was never built, and rewriting the proposal to satisfy a linter
would falsify the record. `tests/` and `benchmarks/` are exempt because
exercising and measuring internals is what internals are for. The exemptions
are listed with their reasons in a test, so widening them is an edit.

**Nothing is promoted.** All 280 exports are `provisional`. Classifying an
adapter's surface records that it is a deliberate entry point; it creates no
compatibility promise, and pre-stable work makes none.

## Consequences

- Adding, removing, renaming or reordering an export in any distribution fails
  the release gate until its classification is reviewed.
- A new public module in any distribution fails the gate until it is
  classified, in the same way a new core module already did.
- `agnara-cli` consumers importing one of the thirteen removed names break.
  The changelog records the removal and the private module each name lives in,
  per ADR 0021; Task 12's migration guide carries the same list.
- The HTTP-specific surface test in
  `tests/architecture/test_public_http_surface.py` keeps its hand-written tuple
  and its stricter rule that no public name may originate in a private module.
  It is now a *narrower* rule on top of the manifest rather than a parallel
  mechanism.
- `docs/MATURITY.md` keeps its per-distribution counts. A count is a summary of
  the manifest, not a substitute for it.
- I9 becomes `IMPLEMENTED` for classification and stays open for stability
  promotion, which the `1.0.0` release gates own.

## Alternatives considered

**One manifest file per distribution.** Rejected: seven files with seven
schemas to validate, and no place for the workspace-level invariant that every
shipped distribution is present. The gap this ADR closes was precisely a
missing entry, and a per-file layout makes a missing file indistinguishable
from a distribution that does not exist.

**Keep `schema_version` 2 for the core and add a second mechanism for
adapters.** Rejected. Two mechanisms is how `agnara-http` came to be governed
by a tuple in a test while the core was governed by a manifest, and it is why
`agnara-mcp` was governed by neither.

**Leave `agnara-cli` at 17 names and classify them.** Rejected. Classification
records a deliberate decision, and there was none: the names were reachable
because `__init__` imported them, not because anyone offered them. Classifying
them would turn an accident into a commitment and make the a4 dogfooding
examples that follow harder to keep honest.

**Extend the private-import rule of ADR 0071 to every distribution — no public
name may originate in a private module.** Rejected as the general rule.
`agnara-cli` is a command whose implementation lives entirely under
underscore-prefixed modules, and satisfying the rule would mean inventing a
public module to hold four integers and a function. The manifest already makes
an accidental export fail, which is the property that matters.

**Audit imports by importing the tree.** Rejected for the same reason ADR 0067
gave: a gate must not import the code it is judging, and an application being
audited may not even be installable in the auditor's environment.
