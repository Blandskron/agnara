# Agnara Git Workflow

## Purpose

Agnara is an agent-first and human-friendly project.

GitHub is not only a remote repository. It is the execution ledger for software development.

Every meaningful change should be traceable through:

```text
Backlog
→ GitHub Issue
→ Branch
→ Implementation
→ Tests / Quality Gates
→ Commit
→ Attribution verification
→ Push
→ Pull Request
→ Review
→ Merge
→ Issue closure
→ Branch cleanup
```

The workflow must work for both autonomous coding agents and humans.

## Sources of truth

Different artifacts own different concerns:

- `BACKLOG.md`: product/architecture roadmap and planned work.
- GitHub Issues: executable units of work and discovered defects/tasks.
- Git branches: isolated implementation state.
- Pull Requests: integration, review and evidence boundary.
- ADR/RFC: architectural decisions.
- CI: objective quality evidence.
- Git history: immutable record of accepted change.
- Issues/PRs/reviews: role and contribution evidence for agents that cannot be
  represented by a verified Git identity.

Do not use one artifact as an accidental replacement for all others.

## AI-agent attribution policy

Git authorship, implementation roles and review roles are related but not
interchangeable.

For human-directed work, keep the human as primary commit author. Add
`Co-authored-by: Name <email>` for an agent only when the agent materially
authored the change and the exact identity is both authorized for Agnara and
verifiably linked to its GitHub user/bot account. A plausible model/provider
name or email is not evidence. Do not add a different agent without evidence
that it actually participated.

A fully autonomous bot with a verified, authorized GitHub identity may be the
primary author. Do not impersonate a human and do not repeat a primary author
as a co-author.

Review-only participation belongs in the PR review/comment trail, not normally
in a co-author trailer. An agent that also makes a material implementation
change may be credited for that work under the same verification rule.

When an agent is not GitHub-verifiable, omit the trailer and document in the
Issue or PR:

```text
Agent
Role
Contribution
Identity verified for GitHub attribution: no
Co-authored-by trailers included: none
Non-verifiable agents documented
```

Git history remains the accepted authorship record; PR artifacts explain roles
and limitations. Do not maintain a duplicate AI-contributors ledger. Do not
rewrite published history to retrofit this policy. See
`docs/adr/0019-ai-agent-attribution.md`.

## Branch model

Protected long-lived branches:

```text
main
develop
```

### `main`

Represents releasable/certified history.

Normal feature work does not target `main`.

Allowed incoming PRs:

- `release/*`
- `hotfix/*`
- exceptionally documented repository-governance changes when no `develop` exists yet

### `develop`

Integration branch for reviewed work intended for the next release.

Normal task branches start from the latest remote `develop` and target `develop`.

## Short-lived branches

Format:

```text
<type>/<issue-number>-<short-slug>
```

Examples:

```text
feat/42-capability-registry
fix/57-provider-scope-cleanup
docs/61-mcp-version-policy
refactor/74-execution-plan-boundary
perf/81-router-benchmark
test/95-free-threading-regression
chore/104-ci-python-314
security/117-redact-trace-secrets
```

Allowed standard types:

```text
feat
fix
docs
refactor
perf
test
chore
security
```

Special branches:

```text
release/v0.1.0
hotfix/123-critical-auth-bypass
```

Do not create personal branches such as:

```text
bastian-work
agent-changes
temp
new
test2
```

## GitHub Issue policy

Every meaningful change needs an Issue before implementation unless it is:

- a trivial typo fixed inside an already-scoped PR;
- a mechanical correction required to make the current Issue pass acceptance;
- an emergency repository recovery where issue creation is temporarily impossible.

When an Issue is created from a backlog item, include the backlog ID.

Example title:

```text
[E1.3] Implement @app.capability registration
```

Issue body must contain:

```text
Context
Backlog reference
Goal
Scope
Out of scope
Acceptance criteria
Architecture constraints
Validation plan
Dependencies / blocked-by
```

## Discovered work

During implementation, an agent may discover new work.

### If required to complete the current Issue

Document it in the current Issue/PR and implement only the minimum necessary related change.

### If independent or out of scope

Create a new Issue and continue the current task.

### If blocking

Create a blocking Issue, link the dependency, mark the current Issue as blocked, and work on the blocker if it is the highest-priority actionable item.

### Security findings

Do not publish exploitable security details in a public Issue.

Follow `SECURITY.md` and use the repository's private vulnerability process when available.

## Start-of-session protocol

Every autonomous development session begins by checking repository state before selecting new work.

Minimum:

```bash
git status --short
git branch --show-current
git fetch --all --prune
gh auth status
gh pr list --state open
gh issue list --state open
```

Then:

1. inspect open PRs with failing checks, requested changes or merge conflicts;
2. resolve actionable existing work before creating unnecessary new work;
3. inspect blocked/high-priority Issues;
4. select the next valid backlog/Issue item.

An agent must not blindly create a new branch when existing unfinished work should be completed first.

## Normal feature/fix flow

### 1. Synchronize

```bash
git switch develop
git fetch origin
git reset --hard origin/develop
```

Only use the hard reset when the working tree is clean or all local work is intentionally disposable.

Never destroy unknown local work.

### 2. Create or select Issue

If the backlog task has no GitHub Issue, create one.

Example:

```bash
gh issue create \
  --title "[E1.3] Implement @app.capability registration" \
  --label "type:feature" \
  --body-file /tmp/issue.md
```

### 3. Create branch

```bash
git switch -c feat/42-capability-registration
```

### 4. Implement

Work only within Issue scope.

Keep `BACKLOG.md` synchronized with actual progress.

Use `[~]` only while the corresponding work is active.

### 5. Validate

Run focused tests during implementation.

Before PR, run all quality gates required by the affected area.

### 6. Commit

Use Conventional Commit style.

Examples:

```text
feat(core): add immutable capability registration
fix(cli): prevent scaffold overwrite
docs(architecture): define delegation boundary
test(core): cover dependency cycle detection
perf(runtime): reduce invocation allocations
chore(ci): add Python 3.14t experimental lane
```

Commit messages should explain coherent changes, not narrate every file.

### 7. Verify attribution

Identify the actual contributors and roles before committing. After commit,
inspect the primary author, complete message and parsed trailers:

```bash
git show -s --format=full HEAD
git show -s --format=%B HEAD | git interpret-trailers --parse
```

Confirm that every trailer is material, authorized and GitHub-verifiable;
that non-verifiable agents are prepared for PR/Issue documentation; and that
no primary author is duplicated. Preserve legitimate existing trailers when
amending or rebasing.

### 8. Push

```bash
git push -u origin feat/42-capability-registration
```

### 9. Create PR

Target `develop`.

PR title should follow Conventional Commit semantics.

Body must contain:

```text
Summary
Issue
Architecture impact
Implementation
Tests / checks
Security impact
Performance impact
Documentation
Breaking changes
AI / Agent contribution (optional for human-only work)
Checklist
```

Use:

```text
Closes #42
```

to link the Pull Request to its Issue.

**This does not close the Issue on its own.** GitHub only auto-closes a
linked Issue when the Pull Request merges into the repository's *default*
branch. Normal Agnara work merges into `develop` while `main` stays the
default, so the keyword creates the link and nothing more.

Close the Issue explicitly after merging. See step 12.

### 10. Review gate

Review the complete diff, not only the final commit.

Inspect:

```bash
gh pr diff <number>
gh pr checks <number>
```

Resolve all actionable review comments and failed checks.

### 11. Merge

Normal task PRs should prefer squash merge to keep `develop` history concise:

```bash
gh pr merge <number> --squash --delete-branch
```

Use auto-merge when configured and all required gates are objective:

```bash
gh pr merge <number> --squash --delete-branch --auto
```

Never bypass failing required checks merely to continue.

Before squash merge, inspect the proposed final subject/body. GitHub is not
assumed to preserve trailers from branch commits. If legitimate trailers
exist, pass an explicit reviewed squash message and place each trailer after a
blank line at the end:

```bash
gh pr merge <number> --squash --delete-branch \
  --subject "<conventional subject>" \
  --body-file /tmp/reviewed-squash-message.md
```

Do not copy unverified trailers forward. Do not omit a verified legitimate
trailer merely because the branch is being squashed.

### 12. Synchronize after merge

```bash
git switch develop
git pull --ff-only origin develop
git fetch --prune
```

Then close the Issue, because merging into `develop` does not:

```bash
gh issue close 42 --comment "Delivered by #43, merged as <sha>."
```

The closing comment should record which Pull Request delivered the work,
the merge commit, and confirmation that the acceptance criteria are met. An
Issue closed with no explanation loses the evidence a later reader needs.

Confirm the Issue is closed and `BACKLOG.md` matches reality.

Then select the next Issue.

## Pull Request review model

GitHub does not permit a Pull Request author to approve their own PR.

Agnara supports two autonomous modes.

### Mode A — Dual-agent review (preferred)

Use distinct GitHub identities:

```text
Implementation Agent
Reviewer Agent
```

Flow:

```text
Implementation Agent
→ branch
→ code
→ tests
→ PR

Reviewer Agent
→ inspect Issue
→ inspect architecture
→ inspect diff
→ run/inspect checks
→ APPROVE or REQUEST CHANGES

Implementation Agent
→ address feedback

Reviewer Agent
→ re-review

→ merge when rules pass
```

The reviewer must not approve merely because checks are green.

Review must consider:

- correctness;
- architecture boundaries;
- tests;
- security;
- concurrency;
- public API;
- documentation;
- backward compatibility;
- performance implications.

### Mode B — Single-agent autonomous operation

If only one GitHub identity is available:

- the agent still MUST create a PR;
- the agent performs a fresh independent self-review pass;
- it may leave a review comment summarizing findings;
- it MUST NOT pretend to provide a GitHub approval;
- repository rules should require PR + status checks but zero mandatory peer approvals;
- auto-merge may occur only after all objective required checks pass and all conversations are resolved.

Once a second independent agent identity exists, migrate to Mode A and require at least one independent approval.

## Self-review protocol

Before any autonomous merge, the agent must switch mental role from implementer to reviewer and re-evaluate from the Issue and diff.

Review questions:

```text
Does the change actually satisfy the Issue?
Did scope expand unnecessarily?
Is core still transport-neutral?
Are package dependency directions correct?
Are there hidden breaking changes?
Are errors protocol-neutral where required?
Are new dependencies justified?
Are concurrency assumptions safe?
Are tests meaningful?
Are docs synchronized?
Are security-sensitive paths covered?
Are performance claims evidenced?
```

If review finds a defect:

1. do not merge;
2. document the finding on the PR;
3. correct it on the same branch if in scope;
4. rerun gates;
5. review again.

## Pending Pull Requests

At the beginning of every work cycle:

- inspect open PRs before taking new work;
- if a PR has requested changes, address it before starting another unrelated Issue;
- if a PR is green and mergeable, complete its review/merge flow;
- if blocked by external conditions, document the blocker and continue with the next independent Issue.

Do not accumulate abandoned agent PRs.

## Reviewing PRs authored by another identity

An authorized agent may review a PR it did not author.

Use:

```bash
gh pr review <number> --approve
```

or:

```bash
gh pr review <number> --request-changes --body "..."
```

Approval requires actual review.

Never approve based only on the PR description.

## Release flow

Release branch starts from `develop`:

```bash
git switch develop
git pull --ff-only origin develop
git switch -c release/v0.1.0
```

Release branch may contain only release preparation:

- version;
- changelog;
- release notes;
- final compatibility fixes;
- packaging metadata.

No unrelated feature work.

Create PR:

```text
release/v0.1.0 → main
```

Prefer a merge strategy that preserves the release relationship rather than squashing the entire release history blindly.

After merge:

1. tag the released commit;
2. publish GitHub Release when applicable;
3. propagate any release-only commits back into `develop` through a PR;
4. delete the release branch.

## Hotfix flow

Hotfix starts from current remote `main`:

```bash
git switch main
git pull --ff-only origin main
git switch -c hotfix/123-critical-description
```

Flow:

```text
Issue
→ hotfix branch from main
→ tests
→ PR to main
→ review
→ merge
→ release/tag if required
→ PR/propagation to develop
```

A hotfix is only for urgent defects affecting the releasable/current production line.

Do not use `hotfix/` as a shortcut around `develop`.

## Merge conflict policy

Agents may resolve conflicts autonomously.

Before resolution:

1. understand both sides semantically;
2. inspect related tests/history/docs;
3. preserve intended behavior from both branches when compatible;
4. never choose `ours` or `theirs` mechanically.

After resolution:

- rerun affected tests;
- rerun architecture checks;
- document non-trivial conflict decisions in the PR.

## Branch protection / rulesets

`main` and `develop` are protected by active rulesets. The exact definitions
live in `.github/rulesets/` so the enforced configuration is reviewable here
and not only in GitHub settings.

Both branches enforce:

- Pull Request required, so direct pushes are rejected;
- the aggregate `CI` status check must pass before merge;
- review conversations must be resolved;
- force pushes rejected;
- branch deletion blocked;
- merge methods limited to squash and merge commit.

Verified by attempting each violation:

```text
git push origin develop
  ! [remote rejected] develop -> develop
  - Changes must be made through a pull request.
  - Required status check "CI" is expected.

git push --force origin main:develop
  ! [remote rejected] main -> develop
  - Cannot force-push to this branch
```

### Required approvals are zero, deliberately

`required_approving_review_count` is `0`.

GitHub does not permit a Pull Request author to approve their own Pull
Request. While Agnara runs on a single agent identity, any non-zero value
would make the repository impossible to merge into. Raise it to `1` when an
independent reviewer identity exists (`BACKLOG.md` E0B.9); that single change
moves the repository from Mode B to Mode A.

Zero required approvals is not the same as no review. Merge still requires a
green `CI`, resolved conversations, and the documented self-review pass.

### No bypass actors

`bypass_actors` is empty, so no one pushes past the rules silently. An admin
can still edit or disable a ruleset in settings for a genuine emergency,
which is visible and auditable in a way a per-push bypass is not.

Never configure a required approval rule that makes a single-agent repository impossible to merge autonomously.

Never weaken branch protections simply to bypass a failing PR.

## CI ownership

The agent owns fixing CI failures caused by its changes.

A red CI run is work in progress, not a reason to merge anyway.

If failure is unrelated/flaky:

1. investigate;
2. gather evidence;
3. create/link an Issue;
4. retry only when justified;
5. do not disable checks silently.

## Pull Request size

Prefer small reviewable PRs.

One Issue → one branch → one PR is the default.

Bundle multiple backlog tasks only when technically inseparable, and list every covered item in the Issue/PR.

## Draft Pull Requests

Use draft PRs for:

- long-running work;
- early architecture review;
- risky refactors;
- work requiring feedback before completion.

Do not use drafts merely as remote backups.

## Autonomous authority

An authorized Agnara agent may autonomously:

- inspect Issues and PRs;
- create Issues;
- assign/label Issues where permissions exist;
- create branches;
- modify code/docs/tests;
- create commits;
- push short-lived branches;
- create PRs;
- review PRs authored by another identity;
- request changes;
- approve PRs authored by another identity;
- enable auto-merge when gates are satisfied;
- merge eligible PRs;
- delete merged short-lived branches;
- create release/hotfix branches;
- update backlog/documentation;
- create ADRs/RFCs;
- open follow-up Issues.

It must not:

- approve its own PR;
- fabricate review;
- bypass required checks;
- force-push protected branches;
- push normal feature work directly to `main` or `develop`;
- silently weaken repository governance;
- publish secrets or exploitable vulnerability details;
- merge known failing work.

## Human-friendly requirement

Autonomy must not make the repository opaque.

Every autonomous action must leave a normal GitHub trail that a human developer can inspect:

```text
Issue
Branch
Commits
PR
Review
CI
Merge
Docs
```

Agents should behave like disciplined maintainers, not hidden automation.
