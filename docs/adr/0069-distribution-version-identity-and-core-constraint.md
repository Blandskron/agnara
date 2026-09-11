# ADR 0069 — Distribution Version Identity and Core Constraint

- Status: Accepted
- Date: 2026-09-11
- Tracking: GitHub Issue #280
- Amends: ADR 0021

## Context

An adapter built from `develop` must not resolve an unrelated published core.
All first-party projects form one tested workspace and the next public target
is `1.0.0`.

## Decision

Every first-party adapter requires exactly the synchronized core version:

```text
agnara-http <workspace version> -> agnara==<workspace version>
```

The rule applies to both the unpublished `<target>.dev0` workspace and an
exact public release. A compatible range is not a supported compatibility
claim until cross-version evidence and a later ADR establish one.

The repository version-transition tool performs the following atomic changes:

- every first-party `project.version`;
- every adapter requirement on `agnara`;
- `uv.lock`;
- the selected target recorded in release governance.

It plans and validates the complete change before writing, supports a
check-only mode, and refuses a partially synchronized workspace. Release gates
verify built metadata and clean installation of the complete locally built
workspace set.

## Consequences

An adapter cannot silently bind to a differently versioned core, and
unpublished work has a distinct package identity from the public baseline.
The trade-off is intentional: adapter artifacts must be installed with their
matching core artifacts until compatibility ranges are supported by evidence.

## Revisit when

Revisit after `1.0.0` only if cross-version compatibility is explicitly tested
and a bounded range would accurately describe that evidence.
