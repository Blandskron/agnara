# ADR 0069 — Distribution Version Identity and Core Constraint

- Status: Proposed
- Date: 2026-09-07
- Tracking: GitHub Issue #280
- Answers: RFC 0007
- Amends: ADR 0021

## Context

ADR 0021 gives all seven first-party distributions one synchronized pre-1.0
version, but leaves two independently necessary rules unspecified:

1. what core versions an adapter accepts in its package metadata;
2. what version the workspace carries on `develop` between releases.

Today every adapter declares an unbounded `agnara` dependency, and `develop`
keeps the last published version until the next release branch changes it.
RFC 0007 records the resulting failure. Installing an adapter wheel built from
`develop` by itself allows the resolver to select the published core with the
same version string even though the two contain different APIs. An exact pin
to that unchanged string produces the same failure.

The two rules must therefore be decided and implemented together. A constraint
cannot distinguish builds with the same version, while a distinct development
version does not prevent an adapter from accepting a differently versioned
core.

## Decision

### Alpha adapters require the exact synchronized core version

Every first-party adapter declares:

```text
agnara==<its own project.version>
```

This rule applies to release and development versions. For example:

```text
agnara-http 0.1.0a4.dev0  →  agnara==0.1.0a4.dev0
agnara-http 0.1.0a4       →  agnara==0.1.0a4
```

An adapter may declare additional adapter-owned dependencies, such as the MCP
SDK or OpenTelemetry API. The exact rule concerns only its dependency on the
first-party core.

The alpha public surface is provisional (ADR 0067), so Agnara makes no claim
that adapters compiled and tested with one workspace version work with another
alpha. A compatible range would claim precisely that. Exact equality is the
only constraint supported by current evidence.

### `develop` carries the current target as `.dev0`

Once a release is published and the owner selects the next
`release-status.json` `current_target`, all seven project versions on
`develop` become:

```text
<current_target>.dev0
```

For the current target, that means `0.1.0a4.dev0`. A release branch replaces
the synchronized development version with the exact public target,
`0.1.0a4`, before building candidate artifacts.

The `.dev0` suffix is constant through one development cycle. It distinguishes
unpublished work from the public release; it does not claim that every commit
on `develop` has a unique package version. Development artifacts are never
published to the public index and must be installed as one built workspace
set. Commit identity remains the evidence identity for CI and release records.

This uses a PEP 440 development release rather than a local version. The
current target is already an explicit release-governance decision, and naming
it in package metadata makes that decision checkable. A local version such as
`0.1.0a3+dev` would describe a downstream rebuild of the old release rather
than development toward the selected next one.

### The transition is one atomic workspace operation

The implementation must provide repository-owned tooling with two operations:

```text
development <target>  →  <target>.dev0
release <target>      →  <target>
```

Each operation updates and validates, as one reviewed change:

- all seven `project.version` values;
- all six adapter requirements on `agnara`;
- `uv.lock`;
- the consistency between development target and
  `docs/releases/release-status.json` where that check applies.

The tool plans and validates the complete edit before its first write, refuses
an invalid or partially matching workspace, supports a check-only mode, and
reports every file it would change. An interrupted or rejected transition is
recovered by reverting its ordinary Git change; a published version is never
overwritten, deleted or reused.

Manual version sweeps cease to be the supported release procedure once the
tool lands. `docs/MAINTAINERS_RELEASE.md` and `GIT_WORKFLOW.md` must call the
tool rather than instructing maintainers to edit thirteen related values by
hand.

### Gates fail closed

Implementation is complete only when executable checks prove all of these:

1. every first-party project version is identical;
2. every adapter's normalized core requirement is exact and equals that
   version;
3. a development workspace version equals `<current_target>.dev0`;
4. a release candidate version equals `<current_target>` and contains no
   development or local suffix;
5. built metadata preserves the exact core requirement;
6. the clean installation gate installs the complete locally built workspace
   set and does not satisfy a first-party requirement from an index;
7. the lockfile is current after either transition.

The current check that an adapter merely mentions `agnara` is insufficient and
must be replaced, not supplemented with a second parser that can disagree.

### Migration order

The implementation PR performs one indivisible migration:

1. add the version-transition tool and focused failure tests;
2. teach release-readiness and installed-distribution checks the exact rule;
3. move all project versions to the current target's `.dev0` version;
4. replace all six unbounded requirements with exact synchronized pins;
5. refresh `uv.lock`;
6. run build and isolated installation tests with all seven wheels;
7. update the operational release documents.

Steps 3 and 4 never land separately. Until that PR merges, the reproduced
substitution remains a known defect and adapter distributions remain
unpublishable.

## Consequences

### Positive

- An adapter cannot silently bind to a differently versioned alpha core.
- A build from `develop` no longer has the same public identity as the last
  released code.
- Installing one development adapter wheel without its matching core fails
  resolution instead of importing an incompatible public core.
- Version and requirement changes become one deterministic, reviewable
  operation.
- Release and installed-artifact gates verify the rule that package metadata
  promises.

### Negative

- Every synchronized version transition changes thirteen values plus the
  lockfile.
- A development adapter wheel is intentionally not independently installable
  unless its matching development core artifact is available.
- `.dev0` identifies a development cycle, not a unique commit; arbitrary
  artifacts from different commits in that cycle must not be mixed.
- Exact pins prevent compatible cross-version combinations even where they may
  happen to work.

The last cost is appropriate during alpha because compatibility is not yet a
supported claim.

## Alternatives considered

### Keep the core dependency unbounded

Rejected. It permits every future core version and contradicts synchronized
workspace testing.

### Use an exact pin but leave `develop` on the last release

Rejected by reproduction. `agnara==0.1.0a3` selects the incompatible published
`0.1.0a3` when both builds carry that string.

### Give `develop` a distinct version but keep the dependency unbounded

Rejected. The immediate same-string substitution disappears, but an adapter
still declares every future core compatible.

### Use a compatible range or lower bound

Rejected during alpha. ADR 0067 classifies the public surface as provisional;
no evidence supports a cross-alpha compatibility promise.

### Use `<last-release>+dev`

Rejected. A local segment describes a variant of the last public version, does
not name the selected target, and has less conventional ordering semantics for
this workflow than a development release.

### Derive a unique version from every commit

Deferred. It would require dynamic build metadata and a policy for exact
requirements whose value depends on the commit that contains them. The current
defect is a collision with a published release, and `<target>.dev0` removes
that collision without introducing a build backend or source-control version
plugin.

## Revisit when

At `0.1.0b1`, after the supported public API and compatibility policy exist,
measure whether adjacent versions are intentionally compatible. A bounded
range may replace exact equality only through a new ADR backed by cross-version
tests. Reaching beta does not change the constraint automatically.

