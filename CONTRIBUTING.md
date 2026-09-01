# Contributing

## Before coding

Read:

1. `VISION.md`
2. `PRINCIPLES.md`
3. `ARCHITECTURE.md`
4. relevant RFCs and ADRs
5. `BACKLOG.md`

## Architecture rule

A pull request that works but breaks dependency direction is not acceptable.

## Workflow

1. choose or create a backlog item;
2. mark it in progress;
3. identify affected package boundary;
4. add or update tests first where practical;
5. implement the smallest coherent change;
6. run quality gates;
7. update docs/ADRs when behavior changed;
8. mark backlog item complete only after acceptance passes.

## API changes

Public API additions require at least one example in `docs/API_DESIGN.md` or a dedicated RFC.

## New dependencies

Every runtime dependency added to `agnara-core` requires explicit justification.

Questions to answer:

- Why standard library is insufficient?
- Can this live in an adapter?
- What is the maintenance risk?
- Does it support Python 3.14?
- Does it support free-threaded Python?
- What happens if it becomes unmaintained?

## Commit scope

Commits should be coherent and reviewable.

Do not mix architecture cleanup, formatting, unrelated refactors and feature behavior unless necessary.

## Documentation

Documentation is part of the implementation.

When actual behavior differs from an RFC or ADR, update the decision record rather than leaving contradictory documentation.

## Changelog

Every PR makes an explicit changelog decision.

Add one concise outcome-oriented entry under `CHANGELOG.md` `[Unreleased]`
when the change affects public API/behavior, configuration, CLI output,
schemas/protocols, dependencies, security, performance claims,
deprecations/removals, migrations or the contributor workflow.

Tests, internal refactors or editorial corrections may omit an entry when they
do not change an observable contract. Select the corresponding PR-template
option and explain why; do not add noise merely to tick a box.

Release maintainers follow ADR 0021 and `GIT_WORKFLOW.md`. All first-party
package versions remain synchronized during v0.x, and `0.0.0` must not be
published.

## Scaffolding changes

Project/app generator changes are public API changes.

Before editing templates, read:

- `docs/APPLICATION_MODEL.md`;
- `docs/CLI_SPEC.md`;
- `docs/SCAFFOLDING.md`.

Template changes require:

- golden-file test updates;
- migration impact review;
- confirmation that generated application/domain layers remain transport-neutral;
- no silent overwrite or deletion behavior.

## Issue-driven Git workflow

All contributors — human or agent — follow `GIT_WORKFLOW.md`.

Default:

```text
Issue
→ short-lived branch
→ implementation / tests
→ commit
→ attribution verification
→ push
→ PR to develop
→ review/checks
→ merge
```

One Issue per PR is preferred.

Do not push feature work directly to `main` or `develop`.

Use Conventional Commit style.

Every PR must link its Issue and describe validation evidence.

## AI / agent attribution

Git history is the source of truth for accepted authorship. PRs and reviews
provide the complementary record of roles, contributions and verification
limitations.

For human-directed work, keep the human as primary commit author. Use a
`Co-authored-by: Name <email>` trailer for an AI agent only when:

- the agent materially authored the change;
- the exact identity is authorized for Agnara;
- the email verifiably maps to that GitHub account; and
- the trailer does not duplicate the primary author.

Do not infer an identity from a model or product name, invent an email, or add
another agent without evidence that it participated. Review-only agents are
credited in the PR review trail, not normally as co-authors.

Place valid trailers after a blank line at the end of the commit message:

```text
docs(governance): define agent attribution

Explain the governance change.

Co-authored-by: Exact Verified Agent <exact-verified-email>
```

The angle-bracketed value is a placeholder and must be replaced only with an
exact verified identity. If an agent lacks one, omit the trailer and complete
the PR template's AI / Agent contribution section with its name, role and
contribution.

Preserve legitimate trailers during amend/rebase or any deliberate commit
recreation, and explicitly carry them into a squash-merge message. Verify the
resulting commit after merge. Do not rewrite historical commits solely to
apply the current policy.

See `GIT_WORKFLOW.md` and `docs/adr/0019-ai-agent-attribution.md` for the
complete evidence and merge rules.
