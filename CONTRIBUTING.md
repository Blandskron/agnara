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

For agent-written work, the materially implementing agent is the primary
commit author. Before committing, read `.github/ai-agent-identities.toml` and
use only its exact registered `git_name` and `email`; do not infer or invent an
identity. Examples presently registered are `Codex <codex@openai.com>`,
`Claude <noreply@anthropic.com>` and
`gemini-cli <218195315+gemini-cli@users.noreply.github.com>`.

Do not make Blandskron the author or a co-author of agent-written commits, and
do not add automatic `Co-authored-by` trailers. If multiple agents make
materially distinct changes, prefer separate commits authored by each verified
agent. Never credit an agent that did not participate, create empty commits or
split trivial work for contribution statistics.

The agent opens or prepares a PR to `develop`, requests formal review from
`Blandskron`, and leaves it unmerged. Blandskron is repository owner,
maintainer, reviewer, governance decision maker and merge authority. A PR
comment or self-review is useful evidence but is not a formal GitHub review;
the maintainer uses GitHub's `Approve`, `Request changes`, or `Comment` review
flow. An agent never approves or merges its own PR.

Before push, verify the result with:

```bash
git log -1 --format=fuller
git log -1 --format=%B
```

The author must be the implementing agent and Blandskron must be absent from
the author and co-author trailers unless he materially implemented part of
that exact commit and explicitly requested credit. Before merge, the
maintainer chooses a method that preserves the verified implementation author;
do not rewrite historical commits solely to apply this current policy.

See `GIT_WORKFLOW.md` and ADR 0092 for the complete workflow and platform
limitations.

## Licensing of Contributions

By submitting a pull request, you agree that your contributions will be licensed under the Apache License 2.0 (see [LICENSE](LICENSE)). No additional Contributor License Agreement (CLA) or Developer Certificate of Origin (DCO) is required at this time.
