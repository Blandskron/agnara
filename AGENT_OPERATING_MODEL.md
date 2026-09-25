# Agent Operating Model

Current repository documentation describes the current framework. Historical release reconstruction must use Git history, tags or GitHub Releases and must not be inferred from active documentation.

Never revive superseded release documentation into current context unless the task explicitly requires historical research.

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
- may provide preliminary evidence or comments;
- does not rewrite history to hide review findings;
- does not replace Blandskron's required formal GitHub review of an
  agent-authored PR.

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
→ REQUEST BLANDSKRON REVIEW
→ WAIT / FIX IF REQUESTED
→ MAINTAINER MERGE
→ RECONCILE
```

The agent repeats this loop rather than waiting for a human to provide every next command.

## Observe

At session start, you MUST coordinate via the MAC protocol:
- Run `python scripts/agent.py status` to understand active work.
- Run `python scripts/agent.py next` to find non-colliding ready tasks.
- If no tasks are found, fall back to inspecting roadmap/backlog and creating new Issues.

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

When an agent materially implements a change, it is the primary commit author.
It must use its exact registered identity from
`.github/ai-agent-identities.toml`; a model name, product name or plausible
provider email is not verification. The agent must not attribute other agents
without evidence of their participation.

Authorized identities live in `.github/ai-agent-identities.toml`. Each agent
is responsible for selecting its own matching entry when it materially
authors a change. Registry membership never causes automatic attribution and
does not authorize one agent to claim another agent's work.

A verified agent must not impersonate a human or duplicate itself as a
co-author. Blandskron is not author or co-author of agent-written commits by
default: his normal contribution is repository ownership, maintenance,
architecture/governance decisions and formal GitHub code review. Separate
commits are preferred when different agents materially author different work.

Review is credited through GitHub's formal review trail. A conversation
comment or implementation self-review does not replace `Approve`, `Request
changes`, or `Comment` in the review flow. An agent opens or prepares the PR,
requests review from Blandskron and leaves it unmerged; agents never approve
or merge their own PRs.

If no verified agent identity exists, preserve transparency by documenting:

```text
Agent
Role
Contribution
Identity verified for commit authorship: no
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

### Agent implementation and human review

Use a PR, objective CI gates and a mandatory self-review, then request formal
review from Blandskron. Self-review is supplementary, never approval. The
versioned ruleset definitions require one approval, dismiss it after a push and
require approval of the last push; GitHub cannot force a named reviewer, so the
PR request and formal review record Blandskron's decision.

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
