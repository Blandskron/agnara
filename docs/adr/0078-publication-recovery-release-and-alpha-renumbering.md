# ADR 0078 — Publication Recovery Release and Alpha Renumbering

- Status: Proposed
- Date: 2026-09-08
- Tracking: GitHub Issue #328
- Release: `0.1.0a5`
- Amends: ADR 0068
- Related: ADR 0021, ADR 0069, ADR 0073, ADR 0079

## Context

`v0.1.0a4` was tagged on reviewed `main` history and its release run passed
every gate the repository owns: the full CI matrix, both CodeQL languages, the
lockfile, the build of all fourteen artifacts, artifact metadata and content
validation, and a clean-room install of all seven wheels with the index closed.

It then published one file.

Workflow run 34285830444 uploaded `agnara-0.1.0a4-py3-none-any.whl` and PyPI
answered `200 OK`. The next file, `agnara_a2a-0.1.0a4-py3-none-any.whl`, was
rejected with `400 Non-user identities cannot create new projects`, which is
what PyPI answers when the authenticated OIDC identity has no pending Trusted
Publisher matching the uploaded project name. Twine uploads every wheel before
any sdist and stops on the first failure, so twelve sibling artifacts *and the
`agnara` sdist* were never uploaded. Post-release verification and the GitHub
Release were later steps of the same job, so both were skipped.

The repository knew this could happen. `docs/releases/v0.1.0a4.md` says the six
pending publishers "still require owner verification", and
`release-status.json` recorded the same thing in a note. Neither statement was
a gate. The release was CODE READY, nothing measured whether it was PUBLISH
READY, and the difference is the whole incident.

## Decision

### `0.1.0a5` is a publication recovery release

It carries the `0.1.0a4` implementation unchanged — no runtime source file
differs — and its scope is the release system: publication ordering,
publish-readiness measurement, post-publication verification, supply-chain
pinning of the publication path, and the documentation of the incident.

Its question is: **can Agnara publish the set it builds, completely, and prove
that it did?**

It is not a feature release, and it must not become one. Anything that changes
runtime behaviour belongs to `0.1.0a6`.

### The Execution Semantics horizon moves to `0.1.0a6`

ADR 0068 gave `0.1.0a5` the streaming model (I2), execution identity and
idempotency behaviour (I3) and performance budgets (I14). That scope moves
intact to `0.1.0a6`, with its guardrails and its gates unchanged. Nothing is
dropped, added or brought forward.

```text
0.1.0a4  →  0.1.0a5  →  0.1.0a6  →  0.1.0b1  →  0.1.0rc1  →  0.1.0
 (partial)   recovery    execution   interop
```

### `0.1.0a4` is history and is not rewritten

The tag is not moved, deleted or recreated. The uploaded wheel is not replaced.
No published file is modified. The changelog section for `0.1.0a4` keeps its
content and gains a statement of what was actually published, because the
history has to be able to say what happened.

`0.1.0a4` is superseded by `0.1.0a5`. Once `0.1.0a5` is published and verified
complete, the recommended disposition for the orphaned `agnara 0.1.0a4` file is
a **yank**, with the reason `Partial multi-distribution publication; superseded
by 0.1.0a5.` A yank leaves the file resolvable for anyone who already pinned it
and removes it from ordinary resolution, which is exactly the intent. Deletion
is not considered: PyPI files are immutable by design and deleting one breaks
anybody who depends on it.

## Alternatives considered

**Reuse or move `v0.1.0a4`.** Rejected outright. A moved tag makes every
recorded evidence commit a lie, and PyPI already holds a file built from the
old one.

**`0.1.0a4.post1`.** Rejected. PEP 440 post-releases exist for changes that do
not affect the distributed code; here the whole point is to distribute thirteen
artifacts that were never distributed. A post-release of an alpha also sorts in
a way most resolvers handle correctly and most humans do not.

**`0.1.0a4.1`.** Not a valid PEP 440 spelling of what was meant, and it would
invent a fourth release-numbering convention in a project that already fixed
one in ADR 0021.

**Fold the recovery into `0.1.0a5 — Execution Semantics` and keep the name.**
Rejected, and this is the substantive alternative. It would mean the release
that first publishes seven distributions is also the release that changes
execution semantics, so a publication failure and a runtime regression would be
indistinguishable in the same version. ADR 0068's own reasoning applies without
modification: a release with two theses proves neither. The cost is one extra
release in the alpha line, which is the same cost ADR 0068 already accepted for
the same reason.

**Publish the six siblings from a one-off manual upload and leave the release
line alone.** Rejected. It would produce distributions that no tagged, verified
pipeline ever built, which is precisely the property Trusted Publishing and the
build-once-promote-the-same-artifact rule exist to prevent.

## Consequences

**Positive.** The alpha line stays honest: a release whose question was
"can this be consumed from outside the repository" is not retroactively also
the release that fixed publishing. `0.1.0a6` inherits Execution Semantics with
its scope intact. The next release to close is small, reviewable and about one
thing.

**Negative.** The path to `0.1.0b1` is one release longer, and every document
that named `0.1.0a5` as the execution release had to be updated. Both are
bookkeeping costs of telling the truth about a numbered line.

**Accepted risk.** `agnara 0.1.0a4` is resolvable on PyPI until it is yanked,
and it advertises adapters that do not exist. The yank is an owner action that
cannot be performed from this repository, so the window is real. ADR 0079
removes the mechanism that created it.
