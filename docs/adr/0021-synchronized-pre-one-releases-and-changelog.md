# ADR 0021 — Synchronized Pre-One Releases and Curated Changelog

- Status: Proposed
- Date: 2026-08-31
- Tracking: GitHub Issue #16

## Context

Agnara is one repository containing seven first-party Python distributions.
Every package currently uses version `0.0.0`, the project has no release tag,
and the Git workflow names release branches without defining how versions,
tags, package metadata and release notes remain consistent.

Independent package versions would add compatibility-matrix and automation
cost before any package has been released. Fully generated release notes, on
the other hand, do not reliably distinguish public behavior from internal
maintenance.

## Decision

### Version line

Through the pre-1.0 development line, all first-party Agnara distributions use
one synchronized PEP 440 version. A release updates every
`packages/*/pyproject.toml` project version together.

Git tags use the exact package version prefixed with `v`:

```text
package version: 0.1.0a1
Git tag: v0.1.0a1
release branch: release/v0.1.0a1
```

Version intent follows semantic-version ordering:

- patch: compatible bug/documentation fixes in the current release line;
- minor: new capability or adapter behavior;
- major: stable-API incompatible change after 1.0;
- `aN`, `bN`, `rcN`: PEP 440 alpha, beta and release-candidate builds.

Before 1.0, a minor release may contain breaking changes, but each one requires
an explicit changelog entry and migration guidance. `0.0.0` remains an
unreleased-development sentinel and must not be published as a release.

### Changelog

`CHANGELOG.md` is the curated project-level release record. It always begins
with `[Unreleased]` and uses only the relevant conventional categories:

```text
Added
Changed
Deprecated
Removed
Fixed
Security
```

Entries describe user/contributor-observable outcomes, link the relevant
Issue or PR, avoid commit-by-commit narration and never disclose embargoed
security details.

A PR requires an Unreleased entry when it changes public API or behavior,
configuration, CLI output, schemas/protocol mapping, dependencies, security,
performance claims, deprecations/removals, migration needs, or contributor
workflow. A test-only, refactor-only or internal documentation change may omit
one, but the PR records why.

### Release preparation

A release branch:

1. selects one PEP 440 version in its tracking Issue;
2. updates every first-party package to that exact version and refreshes the
   lockfile;
3. renames `[Unreleased]` entries to `[version] — YYYY-MM-DD` and creates a new
   empty `[Unreleased]` section;
4. updates changelog comparison links;
5. passes release consistency, full CI and packaging checks;
6. merges to `main`, then receives an annotated `v<version>` tag on the exact
   accepted commit;
7. uses that changelog section as the source for GitHub release notes;
8. propagates release-only commits back to `develop` through a PR.

No package registry publication occurs until credentials, trusted publishing,
license and release gates are separately approved.

Hotfixes follow the same synchronized version, changelog and tag rules from
`main`, then propagate to `develop`.

## Consequences

Positive:

- one version identifies a tested cross-package workspace state;
- release notes are intentional and reviewable;
- tags, package metadata and changelog sections can be checked mechanically;
- the process supports alpha/beta/RC releases without pretending stability;
- release automation can be added later against a defined contract.

Negative:

- a change in one package increments every first-party package version;
- the central changelog can conflict when many PRs edit it concurrently;
- maintainers must decide whether each PR is release-note-worthy;
- independent package cadence is deferred.

## Guardrails

- never publish `0.0.0`;
- never create a release tag before required checks pass;
- never move or reuse a published release tag;
- never release packages with mismatched versions;
- never generate security release notes that expose an embargoed issue;
- never claim a release/hotfix flow was validated without actual evidence;
- never publish packages until license and publishing authorization exist.

## Revisit when

- first-party packages need demonstrably independent release cadences;
- changelog conflicts justify reviewed change fragments;
- trusted publishing and artifact provenance are implemented;
- the project approaches a stable 1.0 compatibility promise.
