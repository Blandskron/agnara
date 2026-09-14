# Maintainer Release Guide

## Release posture

`0.1.0a8` is the retained publication baseline. It is not a recurring preview
cadence. The next authorized public release is `1.0.0`, after its documented
quality gates pass.

Do not create a release merely to produce another version. A release represents
a tested, reviewable product increment.

## Preparing 1.0.0

1. Confirm the release issue and `docs/releases/release-status.json` list every
   required gate as satisfied with reproducible evidence.
2. Start the release branch from the reviewed `develop` tip. Restrict it to
   release preparation and final compatibility fixes.
3. Run `python scripts/set_workspace_version.py release 1.0.0`, then its
   check-only mode. Do not edit synchronized versions manually.
4. Move user-visible `[Unreleased]` items into the dated `1.0.0` changelog
   section and write `docs/releases/v1.0.0.md` from that record.
5. Run the full quality, package-build and clean-install gates.
6. Merge the reviewed release PR to `main`.

## Publication

Dispatch the repository publication workflow from the accepted `main` commit.
The workflow is the only publisher: it validates the selected version, waits
for the protected registry authorization, publishes the synchronized artifacts,
verifies index visibility, and only then creates the immutable tag and GitHub
release. See ADR 0082.

Never create or push a release tag by hand. Never retry by overwriting a
published version. A failed run is investigated and corrected through an Issue
and PR before a new authorized attempt.

## After publication

Propagate release-only changes back to `develop` through a PR. Then select the
next target and transition `develop` to its `.dev0` identity with the version
tool. Record the release evidence in the issue and close it only after the
propagation is merged.

## Emergency fixes

An urgent production defect starts from `main` on a documented hotfix branch.
It still requires an Issue, review, tests, synchronized version selection,
publication authorization and propagation to `develop`. A hotfix is not a
shortcut around those controls.
