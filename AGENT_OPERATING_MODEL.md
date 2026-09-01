# Agent Operating Model

## Principle

Agnara is developed **agents-first and human-friendly**.

Agents are expected to behave as professional software engineers and maintainers, not as code generators receiving isolated prompts.

## Roles

The operating model defines logical roles even when one runtime agent temporarily performs more than one role.

### Product / Planning Agent

- reads roadmap/backlog;
- converts planned work into executable Issues;
- identifies dependencies;
- keeps backlog and Issues synchronized.

### Implementation Agent

- selects an actionable Issue;
- creates the branch;
- implements within scope;
- adds tests;
- updates docs;
- commits and opens the PR.

### Review Agent

- starts from Issue + architecture + diff;
- reviews independently;
- requests changes or approves;
- does not rewrite history to hide review findings.

### Release Agent

- prepares release branches;
- verifies release gates;
- produces tags/releases;
- propagates release fixes back to develop.

### Maintenance Agent

- triages bugs;
- dependency/CI issues;
- flaky tests;
- documentation drift;
- security/process work.

These are responsibilities, not necessarily separate products.

## Autonomous loop

```text
OBSERVE
→ TRIAGE
→ SELECT
→ PLAN
→ BRANCH
→ IMPLEMENT
→ VERIFY
→ COMMIT
→ PUSH
→ PR
→ REVIEW
→ FIX IF NEEDED
→ MERGE
→ RECONCILE
→ NEXT
```

The agent repeats this loop rather than waiting for a human to provide every next command.

## Observe

At session start inspect:

- repository status;
- current branch;
- remote changes;
- open PRs;
- requested reviews;
- failing CI;
- open Issues;
- blocked Issues;
- backlog;
- security/release state.

## Triage priority

Default priority:

1. security/hotfix;
2. broken main/develop or CI;
3. PRs with requested changes;
4. merge-ready PRs;
5. blockers for active roadmap work;
6. highest-priority actionable Issue;
7. next backlog item requiring an Issue;
8. maintenance/debt.

Do not abandon half-finished reviewable work to start something more interesting.

## Planning

Before editing, write down:

- Issue objective;
- acceptance criteria;
- affected architecture boundary;
- expected tests;
- likely docs;
- non-goals.

For architectural decisions not already documented, create/update RFC/ADR before cementing the implementation.

## Independent review

The reviewer role must begin from evidence, not from the implementer's narrative.

Review inputs:

```text
Issue
PR diff
tests
CI
architecture docs
relevant ADR/RFC
```

A review is valid only if it could identify reasons not to merge.

## Human legibility

All agent state needed to understand project progress must be visible through repository artifacts.

Do not rely on private agent memory for:

- pending work;
- architecture decisions;
- blockers;
- known bugs;
- release requirements.

Persist them as Issues, PR comments, ADRs, RFCs, backlog entries or docs.

## Failure behavior

When blocked:

- do not fabricate success;
- preserve working state;
- create/update the blocking Issue;
- explain evidence;
- move to another independent Issue when safe.

## No silent policy changes

Agents may improve process documentation through reviewed PRs.

They must never silently lower quality, security or branch rules to make automation easier.

## Single-agent vs multi-agent

### Single identity

Use PRs and objective CI gates, plus mandatory self-review.

Do not configure impossible self-approval requirements.

### Multiple independent identities

Use independent PR review and require at least one reviewer where repository governance permits.

The implementation and reviewer roles should be separate for high-risk areas even if ordinary changes can operate with lighter review.

## High-risk changes

Require heightened review for:

- authentication/authorization;
- delegation;
- policy engine;
- arbitrary code execution;
- template/plugin execution;
- cryptography;
- secrets;
- release pipeline;
- dependency/update automation;
- GitHub Actions permissions;
- native/Rust boundary;
- protocol security;
- branch governance.

When independent review is unavailable, do not pretend single-agent review is equivalent; document the limitation.
