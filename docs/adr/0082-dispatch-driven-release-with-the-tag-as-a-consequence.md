# ADR 0082: Dispatch-driven release with the tag as a consequence of approval

- Status: Proposed
- Date: 2026-09-09
- Release: `0.1.0a8`
- Extends: ADR 0073, ADR 0079, ADR 0081
- Supersedes: ADR 0073 decision 6, ADR 0079 "one more required action before
  tagging"

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
6. `approve-and-tag` -- runs in the protected `pypi` environment, so it waits
   for a required reviewer. After approval it re-checks every precondition,
   creates the annotated tag `v<version>` on the dispatched commit as
   `github-actions[bot]`, pushes it, and verifies it with
   `check_release_tag.py`. It is the only job that may create a tag and the
   only job besides `github-release` that holds `contents: write`.
7. `publish` -- also in the `pypi` environment, with `id-token: write` and
   `contents: read`. Checks out the tag, asserts it names the dispatched
   commit and reviewed `main` history, re-validates the downloaded bundle, and
   uploads one project per step, siblings first and `agnara` last (ADR 0079).
8. `verify-published` -- every project carries both a wheel and an sdist at
   the version, then a clean install of the published set.
9. `github-release` -- created only after step 8, from
   `docs/releases/v<version>.md`, for the tag created in step 6.

The `pypi` environment is entered twice, so a reviewer approves twice: once
to create the tag, once to publish. That is deliberate. Folding both into one
job would put `contents: write` next to the OIDC token, which ADR 0079 removed
on purpose; two approvals a minute apart cost nothing and keep least privilege
per job.

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

**Tag after publication instead of before.** A tag created only after
`verify-published` would leave no tag behind when PyPI rejects an upload. It
also leaves PyPI holding whatever *was* uploaded, which is immutable, so the
version is burned on the index anyway, and the GitHub Release would announce a
tag that did not exist while the upload ran. The owner's stated order --
approve, tag, publish, verify, announce -- is kept, and the residual risk is
named honestly: a PyPI-side rejection after the tag still costs the version.
What this ADR removes is every *repository-side* way of burning one.

**A resumable or partial rerun.** Unchanged from ADR 0079: it needs either
`skip-existing` or a "start from project N" input, both of which hide the
ordinary error.

**A tag ruleset that forbids creation.** The workflow creates the tag with the
run's `GITHUB_TOKEN`, which a ruleset restricting creation would block without
a bypass this token cannot hold. The recommended ruleset restricts *update
and deletion* of `v*` tags -- immutability -- and leaves creation to the
workflow, which is the only creator the documentation names.

## Consequences

- A tag cannot exist without every gate having passed and a human having
  approved, so the `tag created -> UNVERIFIED -> version burned` sequence that
  produced A5 and A7 is structurally impossible.
- A run dispatched from a branch other than `main`, or from a stale head of
  `main`, refuses before building anything.
- The owner's remaining release actions are: read back the seven publishers
  on PyPI and record them; protect the `pypi` environment; press *Run
  workflow*; approve twice. None of them is `git tag`.
- ADR 0073 decision 6 ("manual dispatch may validate and never publish") is
  superseded: dispatch is now the only way to publish, and publication still
  requires the protected environment.
- `v0.1.0a4` to `v0.1.0a7` remain immutable and documented as what they were.
