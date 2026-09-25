# ADR 0082 — Dispatch-driven release with the tag as a consequence

- Status: Proposed
- Date: 2026-09-09
- Related: ADR 0073, ADR 0079, ADR 0095

## Context

Creating a tag before publication consumes an immutable release identity even
when validation or a registry rejects the run. The accepted source commit and
its artifacts need a protected publication chain before any tag is created.

## Decision

`release.yml` is dispatched from `main` with an exact version. It verifies the
remote `main` commit, target metadata, license, changelog, registry state,
artifact inventory and SHA-256 digests. All fourteen artifacts are built from
one accepted commit and installed together in a clean environment before
upload. The `pypi` environment requires a reviewer and restricts deployment
branches. Project-specific environments give each PyPI project a distinct OIDC
publisher identity.

Publication proceeds in three protected phases. `bootstrap-1` uploads
`agnara-a2a`, `agnara-cli` and `agnara-events`; `bootstrap-2` uploads
`agnara-http`, `agnara-mcp` and `agnara-telemetry`; `final` uploads `agnara`.
Every phase verifies the same retained source commit and prior-phase
artifact state before continuing. After all seven projects contain wheel and
sdist, the workflow performs a clean install, creates the annotated tag on the
accepted commit, creates the GitHub Release and publishes the reference image.

No human creates a tag manually. A failed gate prevents later phases and the
tag. A partial registry publication requires investigation and a new version;
artifacts and tags are not replaced.

## Consequences

Protected approval precedes registry writes. The immutable tag describes a
verified publication, and the GitHub Release cannot advertise an incomplete
set. The retained artifact digest chain connects every phase to one commit.
