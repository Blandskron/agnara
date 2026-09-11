# ADR 0021 — Synchronized Stable Releases and Curated Changelog

- Status: Accepted
- Date: 2026-09-11
- Tracking: GitHub Issue #16

## Context

Agnara ships seven first-party Python distributions that form one tested
workspace. The retained A8 publication is a historical baseline; the next
release is the first stable public release, `1.0.0`.

Independent package cadence would introduce a compatibility matrix before the
project has evidence to support it. Release notes also need deliberate human
curation rather than a commit dump.

## Decision

All first-party distributions use one synchronized PEP 440 version. `1.0.0`
is the current target. A release updates every `packages/*/pyproject.toml`
version together, uses the corresponding immutable `v<version>` tag, and is
prepared on a release branch.

Between releases, `develop` carries `<target>.dev0`; this development identity
is never published. The repository-owned version tool updates package versions,
exact adapter-to-core requirements and the lockfile as one validated operation.

`CHANGELOG.md` begins with `[Unreleased]` and records observable outcomes under
the relevant categories: Added, Changed, Deprecated, Removed, Fixed and
Security. A user-visible API, behavior, configuration, security, dependency or
migration change requires an Unreleased entry. Pure internal work may omit one
when the PR explains why.

The release workflow must:

1. select the synchronized target in the tracking issue;
2. move the workspace to the exact public version;
3. date the changelog section and prepare release notes from it;
4. pass full CI, packaging, installation and release-consistency gates;
5. merge the accepted release change to `main`;
6. dispatch publication, which verifies artifacts and creates the immutable tag
   only after authorization succeeds;
7. propagate release-only changes back to `develop`.

## Consequences

One version identifies a fully tested cross-package state, and package
metadata, changelog and tags can be checked mechanically. The cost is that a
release increments all first-party projects and requires intentional changelog
curation. Independent package versions remain deferred until evidence justifies
them.

## Guardrails

- Never publish `0.0.0` or a development version.
- Never create, move or reuse a release tag outside the approved workflow.
- Never publish mismatched first-party package versions.
- Never claim a release gate passed without reproducible evidence.
- Never publish before license, provenance and registry authorization gates
  pass.
