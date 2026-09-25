# Maintainer Release Guide

This guide describes the reusable synchronized publication process. The
[release checklist](releases/RELEASE_CHECKLIST.md) records the target-specific
work; [quality gates](../QUALITY_GATES.md) define required verification.

## Prepare and review

1. Select one target version and create an Issue. Work from reviewed
   `develop` on a release branch. Record the target in
   `docs/releases/release-status.json`.
2. Use `scripts/set_workspace_version.py release <version>` to align all seven
   distributions, exact `agnara` pins and the lockfile. Check the resulting
   metadata and package descriptions.
3. Move the target changes from `[Unreleased]` to a dated changelog entry and
   write `docs/releases/v<version>.md`.
4. Run the full CI, public API, documentation, package build, installed-artifact,
   security and supply-chain gates. Review the exact source commit.
5. Merge the approved release PR to `main` through repository protections.
   Do not create a tag manually.

## Publish the accepted commit

Dispatch `release.yml` from the unchanged `main` commit with the same
`version` input in three separate phases. Each waits for the protected
`pypi` environment approval and verifies the prior phase's immutable
artifact set before continuing:

1. `bootstrap-1`: `agnara-a2a`, `agnara-cli`, `agnara-events`.
2. `bootstrap-2`: `agnara-http`, `agnara-mcp`, `agnara-telemetry`.
3. `final`: `agnara`, verification of all seven PyPI projects, immutable tag
   and GitHub Release, then reference-container publication.

Build and validate all fourteen artifacts from the same accepted commit.
Inspect package metadata and index readback. A failed phase requires
investigation; never overwrite a published version or bypass a protected gate.

## Reconcile

Record published evidence in the Issue. Propagate release-only changes back to
`develop` by PR, then select the next development target through the version
tool. An urgent fix follows the same review, validation, protected publication
and propagation controls. `main` receives no ordinary feature work.
