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
→ PR to develop
→ review/checks
→ merge
```

One Issue per PR is preferred.

Do not push feature work directly to `main` or `develop`.

Use Conventional Commit style.

Every PR must link its Issue and describe validation evidence.
