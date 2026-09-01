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
→ VERIFY ATTRIBUTION
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

## Roles, contribution and Git authorship

Logical role names describe work; they are not GitHub identities.

For every agent-assisted change, identify the agents that actually
participated, their roles and their material contributions. Record that
information in the PR (or Issue when no PR is possible), even when an agent
cannot receive Git-native credit.

In a human-directed session, the human remains the primary commit author. An
agent may receive a `Co-authored-by` trailer only for material authorship and
only when its exact identity is authorized and GitHub-verifiable. A model name,
product name or plausible provider email is not verification. An agent must
not attribute other agents without evidence of their participation.

Authorized identities live in `.github/ai-agent-identities.toml`. Each agent
is responsible for selecting its own matching entry when it materially
authors a change. Registry membership never causes automatic attribution and
does not authorize one agent to claim another agent's work.

A fully autonomous bot with its own verified and authorized GitHub identity
may be the primary author. It must not impersonate a human or duplicate itself
as both primary author and co-author.

Review is credited through the GitHub review/comment trail. A Review Agent is
not normally a co-author unless it also made a material implementation
contribution, in which case that contribution and the identity evidence are
documented separately.

If no verified agent identity exists, preserve transparency by documenting:

```text
Agent
Role
Contribution
Identity verified for GitHub attribution: no
```

and omit `Co-authored-by`.

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
