# ADR 0095 — Synchronized releases and curated changelog

- Status: Accepted
- Date: 2026-09-25
- Tracking: GitHub Issue #512

## Context

Agnara ships seven first-party distributions as one tested workspace. Their
runtime and adapter versions must identify one compatible source commit.
Release notes need deliberate curation rather than a commit dump.

## Decision

All first-party distributions use one synchronized PEP 440 version. A release
updates every `packages/*/pyproject.toml` version, exact adapter-to-core pins
and `uv.lock` together through `scripts/set_workspace_version.py`. The
`0.0.0` sentinel and development versions are never published.

`CHANGELOG.md` begins with `[Unreleased]` and records user-visible API,
behavior, configuration, security, dependency and migration changes. Internal
work may omit an entry when the PR explains why. A release dates its target
section and prepares release notes from that curated text.

The reviewed release change lands on `main` through a protected PR. The
maintainer dispatches the protected publication workflow from the accepted
commit. That workflow validates all seven distributions, installs the built
artifacts together, obtains protected publishing authorization, verifies the
published set, then creates the immutable tag and GitHub Release. Release-only
changes propagate back to `develop` through a PR.

## Guardrails

- Never publish mismatched first-party versions or a development sentinel.
- Never create, move or reuse a release tag outside the approved workflow.
- Never claim a gate passed without reproducible evidence from the exact commit.
- Never publish before license, provenance and registry authorization gates pass.
