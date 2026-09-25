# ADR 0079 — Sequenced publication and publish readiness

- Status: Proposed
- Date: 2026-09-08
- Tracking: GitHub Issue #328
- Related: ADR 0073, ADR 0069, ADR 0082, ADR 0095

## Context

A valid source commit does not prove that every external registry project and
publisher identity is ready. Uploading a batch without per-project checks can
leave a partial synchronized release. The publication process must make both
code readiness and registry readiness explicit.

## Decision

`scripts/check_release_readiness.py` checks repository evidence;
`scripts/check_publication_readiness.py` checks the reviewed publication set,
versions, exact pins, lockfile, artifacts, notes, registry state and publisher
configuration. `docs/releases/publication.json` records verified Trusted
Publisher tuples for the exact project and environment. A manual readback is
required where the registry cannot be inspected automatically.

The protected release workflow uploads sibling distributions before `agnara`
so an incomplete upload cannot expose a new kernel version with missing exact
pinned adapters. Each distribution has its own upload step and identity.
`skip-existing` remains disabled. Verification requires both wheel and sdist
for all seven projects and a clean install of the published set. The GitHub
Release follows verification.

## Consequences

A failed partial publication is investigated and closed by a new version; no
published file or immutable tag is overwritten. The release report names the
project and phase that failed. Publisher readback remains a human responsibility.
