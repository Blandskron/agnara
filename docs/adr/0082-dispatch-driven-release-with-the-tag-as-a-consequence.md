# ADR 0082: Dispatch-driven release with the tag as a consequence of approval

- Status: Proposed
- Date: 2026-09-09
- Release: `0.1.0a8`
- Extends: ADR 0073, ADR 0079, ADR 0081
- Supersedes: ADR 0073 decision 6, ADR 0079 "one more required action before
  tagging"

> Amended for A8 by [ADR 0083](0083-a8-bootstrap-publisher-identities.md):
> `publish` is now approval only; seven sequential upload jobs use distinct
> environments. Schema 3 replaces the shared environment with per-project
> `publisher_environment`. The tag-after-verification decision is unchanged.

## Context

Four consecutive release attempts each consumed a version without publishing
the reviewed set:

| Tag | What happened | What was published |
| --- | --- | --- |
| `v0.1.0a4` | one upload accepted, the second rejected by PyPI | one wheel of fourteen |
| `v0.1.0a5` | publication readiness refused: `publication.json` was `UNVERIFIED` | nothing |
| `v0.1.0a6` | readback recorded, PyPI still rejected `agnara-a2a` | nothing |
| `v0.1.0a7` | publication readiness refused: `publication.json` was `UNVERIFIED` | nothing |

They differ in detail and share one mechanism. `release.yml` was triggered by
a pushed `v*.*.*` tag, so the one irreversible act of a release -- an
immutable, never-reused tag -- happened *first*, by hand, before any gate had
run. Every gate that later said no left behind a tag naming a release that did
not exist. The gates were right each time; their position made them useless
for the thing they existed to protect.

Two root causes are distinct and both have to be closed:

1. **Registry configuration.** PyPI answered `400 Non-user identities cannot
   create new projects` for `agnara-a2a`, which means no Pending Trusted
   Publisher matched that exact project name for the workflow's OIDC identity.
   `agnara_a2a` is the wheel and sdist filename normalization mandated by PEP
   427 and PEP 625; the project name is and remains `agnara-a2a`. The
   repository cannot read PyPI's publisher table, and A6 proved that a human
   readback recorded against a target version can still be wrong.
2. **Release flow.** A JSON field cannot stop a tag that already exists, and a
   maintainer typing `git tag` cannot be made to run the gates first.

## Decision

### The release is a dispatched run from `main`; the tag is its consequence

`release.yml` is triggered only by `workflow_dispatch`, with one input, the
version. It refuses to run on any ref but `refs/heads/main`. Nothing in the
repository instructs a maintainer to create or push a tag by hand any more.

The run is a chain of jobs joined by real `needs`, in this order:

1. `validate` -- the complete `ci.yml` (lint, format, types, tests on three
   platforms, browser evidence, lockfile, build and install, CodeQL).
2. `preconditions` -- `scripts/check_release_preconditions.py`: the run is a
   dispatch from `refs/heads/main`; the checked-out commit is the current
   head of `main` on the remote; the version is a publishable v0.x version;
   no tag `v<version>` exists on the remote or in the checkout; the `pypi`
   environment has required reviewers and restricts which branches may deploy.
   Then `set_workspace_version.py release <version> --check`, `uv lock
   --check`, and offline publication readiness including the OIDC identity
   check below.
3. `build` -- exactly seven wheels and seven sdists, `check_distributions.py`
   against the artifact set, publication readiness against the built set,
   SHA-256 digests retained for ninety days.
4. `test-artifact` -- clean-room install of the seven wheels with the index
   closed, `--require-installed`, every import, every console script.
5. `publish-preflight` -- preconditions again (time has passed), then
   publication readiness `--online --oidc-identity`: no file of this version
   exists anywhere, and the recorded publisher kind of each project agrees
   with whether the project exists.
6. `publish` -- runs in the protected `pypi` environment, so it waits for a
   required reviewer. `id-token: write` and `contents: read`. After approval
   it re-checks every precondition, re-validates the downloaded bundle, and
   uploads one project per step, siblings first and `agnara` last (ADR 0079).
   No tag exists at this point.
7. `verify-published` -- every project carries both a wheel and an sdist at
   the version, then a clean install of the published set.
8. `tag` -- depends on step 7. Re-checks that the checkout is the dispatched
   commit and that `v<version>` still exists nowhere, creates the annotated
   tag on that commit as `github-actions[bot]`, pushes it, and verifies it
   with `check_release_tag.py`. It is the only job that may create a tag, and
   it holds `contents: write` and nothing else. If step 6 or 7 fails, it never
   runs, and no tag exists.
9. `github-release` -- created only after step 8, from
   `docs/releases/v<version>.md`, for the tag created in step 8.

The `pypi` environment is entered once, at `publish`. The tag needs no
separate approval because it is no longer a decision: it records that a
publication was verified, and it cannot exist without one. The dispatched
commit is tagged whether or not `main` has moved during the run, because PyPI
already holds exactly what that commit built; refusing the tag at that point
would leave a published version with no tag, which is worse than a tag behind
the head of `main`.

### The human gate must be real, and the pipeline checks that it is

An environment with no required reviewers approves every run instantly, which
would let the workflow tag and publish with nobody having said yes.
`check_release_preconditions.py` reads the environment's protection rules
through the GitHub API with the run's own read-only token and refuses to
proceed unless a `required_reviewers` rule with at least one reviewer exists
and the deployment branch policy restricts which branches may enter. Those
settings are the owner's to make; the pipeline's job is to notice when they
are missing, before anything irreversible happens.

### `publication.json` records registry facts, not release authorization

Schema 2 of `docs/releases/publication.json` drops `target` and
`verified_for_target`. The file records what should be stable between
releases -- the shared publisher tuple, each project's exact PyPI project
name, whether its publisher is *pending* (project absent) or *active*
(project exists) -- and the human readback of each: who, and on which date.
The per-release authorization is the environment approval above, recorded in
the file as `release_authorization: github-environment / pypi` so the two
mechanisms name each other.

`check_publication_readiness.py` still refuses while any project is
`UNVERIFIED`. It additionally refuses:

- a readback dated before `last_registry_failure.on`, because A6 proved that
  everything read before a failure is void;
- a `verified_by` or `confirmed_by` that names an automation identity, so the
  pipeline can never certify its own configuration;
- a publisher kind that disagrees with the recorded `pypi_state`, and, online,
  with whether the project actually exists on the index;
- a recorded tuple that this repository cannot present: `release.yml` must
  exist and run a job in the `pypi` environment, and inside GitHub Actions
  `GITHUB_REPOSITORY` and `GITHUB_WORKFLOW_REF` must spell the recorded
  repository and workflow (`--oidc-identity`).

The record stays `UNVERIFIED` until the owner reads all seven publishers back
from PyPI after the A6 failure and records the readback. No automation writes
that file; a test asserts the workflow never touches it.

### `0.1.0a8` is release recovery only; Execution Semantics moves to `0.1.0a9`

`0.1.0a8` carries the `0.1.0a7` runtime unchanged. It owns this ADR, the
dispatch-driven workflow, the preconditions script, schema 2 of the
publication record, and the regression tests that hold them. Execution
Semantics -- I2 streaming, I3 execution identity and idempotency behaviour,
I14 performance budgets -- moves intact from `0.1.0a8` to `0.1.0a9`, losing no
scope. `0.1.0b1` and later are unchanged.

## Rejected alternatives

**Tag before publication, right after approval.** This record's first
version did that, with two approvals. It still left one way to burn a version:
a PyPI-side rejection after the tag -- exactly the A4 and A6 failure -- would
have produced an immutable tag with an incomplete or empty publication. Tagging
only after `verify-published` closes it: if any upload fails, or the index does
not confirm all fourteen files, no tag exists and the version can be retried
once the external cause is fixed. PyPI may still hold whatever *was* uploaded,
which is immutable, so a partial upload still costs the version on the index
-- but the repository no longer records a release that did not happen, and
the kernel-last order (ADR 0079) keeps that partial state uninstallable.

**A resumable or partial rerun.** Unchanged from ADR 0079: it needs either
`skip-existing` or a "start from project N" input, both of which hide the
ordinary error.

**A tag ruleset that forbids creation.** The workflow creates the tag with the
run's `GITHUB_TOKEN`, which a ruleset restricting creation would block without
a bypass this token cannot hold. The recommended ruleset restricts *update
and deletion* of `v*` tags -- immutability -- and leaves creation to the
workflow, which is the only creator the documentation names.

## Consequences

- A tag cannot exist without every gate having passed, a human having
  approved, all seven distributions being on PyPI and the index confirming
  them complete, so the `tag created -> UNVERIFIED -> version burned` sequence
  that produced A5 and A7, and the `tag created -> upload rejected` sequence
  that produced A4 and A6, are both structurally impossible.
- A run dispatched from a branch other than `main`, or from a stale head of
  `main`, refuses before building anything.
- The owner's remaining release actions are: read back the seven publishers
  on PyPI and record them; protect the `pypi` environment; press *Run
  workflow*; approve once. None of them is `git tag`.
- ADR 0073 decision 6 ("manual dispatch may validate and never publish") is
  superseded: dispatch is now the only way to publish, and publication still
  requires the protected environment.
- `v0.1.0a4` to `v0.1.0a7` remain immutable and documented as what they were.
