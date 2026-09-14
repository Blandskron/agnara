# RFC 0007 — Distribution Version Identity

- Status: Accepted by ADR 0069
- Date: 2026-09-11

## Problem

A first-party adapter built from unreleased source must not resolve a published
core with a different API under an ambiguous package identity. This is a
package correctness issue, not a transport concern.

## Decision

The workspace has one selected target, currently `1.0.0`. `develop` uses the
distinct `<target>.dev0` identity; release preparation uses the exact target.
Every adapter declares an exact requirement on the matching core version.

The repository version tool changes the complete workspace atomically and
release checks verify both source metadata and built artifacts. Development
artifacts are installed as one local workspace set and are never uploaded to a
public index.

## Alternatives rejected

Leaving an adapter dependency unbounded allows incompatible core selection.
Keeping development source at a published version makes that selection hard to
detect. A local-version suffix does not express the selected next release as
clearly as a PEP 440 development release. Compatibility ranges are deferred
until they are backed by cross-version tests.

## Outcome

ADR 0069 adopts this proposal. The release workflow and package checks are the
executable evidence for the policy.
