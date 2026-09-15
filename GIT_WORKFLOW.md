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
- `CHANGELOG.md`: curated user/contributor-visible outcomes for the next and
  past releases.
- CI: objective quality evidence.
- Git history: immutable record of accepted change.
- Issues/PRs/reviews: role and contribution evidence for agents that cannot be
  represented by a verified Git identity.

Do not use one artifact as an accidental replacement for all others.

## Agent authorship and human review

ADR 0092 governs current work. Git authorship, implementation and review are
related but not interchangeable. When an agent materially implements a commit,
the agent is its primary author and uses the exact registered `git_name` and
`email` from `.github/ai-agent-identities.toml`. Do not infer an identity from
a model/provider label, invent an email, or credit an agent that did not
participate.

Blandskron is repository owner, maintainer, architecture/governance decision
maker, formal reviewer and merge authority. For agent-written commits he is
not the author or a co-author by default. His normal contribution is a formal
GitHub Pull Request review. Do not add automatic `Co-authored-by` trailers;
when several agents materially author separate portions, prefer separate,
accurately authored commits.

The implementing agent opens or prepares a PR to `develop`, requests review
from `Blandskron`, and leaves it unmerged. Self-review and conversation
comments are supplementary evidence only: they never substitute for GitHub's
formal `Approve`, `Request changes`, or `Comment` review flow. Do not create
empty commits/PRs, fabricate reviews or manipulate history for statistics.

If the available GitHub client cannot create the PR as the agent's own
App/bot identity, record that limitation in the PR without falsifying its
creator or commit author. Historical commits and ADR 0019 remain historical
evidence and are not rewritten. Do not maintain a duplicate contributors
ledger.

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

Identify the actual implementing agent and its registered identity before
committing. After commit, inspect the author and complete message:

```bash
git log -1 --format=fuller
git log -1 --format=%B
```

Look up agent identities in `.github/ai-agent-identities.toml`. Use the exact
registered identity only for an agent that materially authored the change. The
author must be that agent, not Blandskron; no automatic co-author trailer is
added. Confirm that Blandskron is absent from author/co-author metadata unless
he materially implemented part of that exact commit and explicitly requested
credit. The registry never establishes participation by itself.

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
Changelog decision
Authorship
Formal maintainer review
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

### 10. Formal maintainer review gate

Review the complete diff, not only the final commit.

Inspect:

```bash
gh pr diff <number>
gh pr checks <number>
```

Resolve all actionable review comments and failed checks.

The implementation agent requests review from `Blandskron`. A normal PR
conversation comment, including a self-review comment, is not a formal review.
The maintainer uses GitHub's **Files changed → Review changes → Approve /
Request changes / Comment** flow. The agent addresses requested changes in a
new commit authored by the same verified agent, then waits for another formal
review. Agents do not approve or merge their own PRs.

### 11. Maintainer merge

Only Blandskron merges an agent-authored PR after his formal review and all
required CI. Before merging, verify the result will preserve the verified
agent implementation author. A merge commit preserves the branch commit;
squash is allowed only when the resulting GitHub author metadata is verified
to remain the implementing agent. Never use a merge method that silently turns
the maintainer into the implementation author, and never bypass failing checks.

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

Every agent-authored PR requires a formal GitHub review by Blandskron. The PR
requests him as reviewer; he evaluates the Issue, architecture, diff, tests,
CI, security, compatibility, documentation and performance implications, then
uses `Approve`, `Request changes`, or `Comment`. Required CI never replaces
that human decision.

A self-review or conversation comment may identify defects and is encouraged,
but it is not a formal review and cannot satisfy the required approval. The
implementation agent fixes requested changes, using its verified agent author
identity, and waits for re-review. An agent never fabricates a review, approves
its own PR or merges it.

## Self-review protocol

Before requesting human review, the agent re-evaluates the Issue and diff.

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

1. do not request merge;
2. document the finding on the PR;
3. correct it on the same branch if in scope;
4. rerun gates;
5. review again.

## Pending Pull Requests

At the beginning of every work cycle:

- inspect open PRs before taking new work;
- if a PR has requested changes, address it before starting another unrelated Issue;
- if a PR is green and awaits Blandskron's review, leave it ready for that review;
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

Read `docs/adr/0021-synchronized-pre-one-releases-and-changelog.md` before
preparing a release. Agnara uses one synchronized PEP 440 version for every
first-party package during v0.x. `0.0.0` is an unreleased-development sentinel
and must not be published.

Release branch starts from `develop`:

```bash
git switch develop
git pull --ff-only origin develop
git switch -c release/v0.1.0a1
```

Release branch may contain only release preparation:

- version;
- changelog;
- release notes;
- final compatibility fixes;
- packaging metadata.

No unrelated feature work.

The release tracking Issue records the selected version and acceptance gates.
On the branch:

1. run `python scripts/set_workspace_version.py release <version>` to update
   every project version, all exact adapter-to-core pins, and `uv.lock` as one
   validated operation;
2. run `python scripts/set_workspace_version.py release <version> --check`;
3. move current `[Unreleased]` entries in `CHANGELOG.md` to
   `[version] — YYYY-MM-DD`;
4. create a fresh empty `[Unreleased]` section and update comparison links;
5. prepare release notes from that versioned changelog section;
6. run the full quality suite, synchronized-version check, package builds and
   install/import smoke tests.

Create PR:

```text
release/v0.1.0a1 → main
```

Prefer a merge strategy that preserves the release relationship rather than squashing the entire release history blindly.

Before merge, inspect the final commit relationship and attribution. After
merge:

1. confirm the accepted `main` commit contains the reviewed version and
   changelog;
2. dispatch the `Release to PyPI` workflow from `main` with that version. Do
   **not** create or push a tag by hand: after every gate has passed and a
   reviewer has approved the run in the `pypi` environment, the run publishes
   the packages through Trusted Publishing and verifies the index, and only
   then creates the one annotated `v<version>` tag on that exact commit; that
   tag is never moved or reused, and it never exists for a failed publication
   (ADR 0082);
3. the same run creates the GitHub Release from `docs/releases/v<version>.md`
   for that tag;
4. propagate any release-only commits back into `develop` through a PR;
5. delete the release branch.

Do not mark E0B.12 complete merely because this process is documented. That
item requires evidence from an actually exercised release and hotfix flow.

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

If a hotfix produces a release, it must:

- select the next compatible synchronized PEP 440 version;
- record it as `current_target`, then use
  `python scripts/set_workspace_version.py release <version>` to update every
  first-party package version, adapter core pin and `uv.lock`;
- add the fix under `[Unreleased]`, then cut the dated changelog section;
- pass the same release consistency, build, CI and attribution gates;
- tag the exact accepted `main` commit with annotated `v<version>`;
- propagate code, version and changelog changes back to `develop` by PR.

After any release propagation, select the next target and run
`python scripts/set_workspace_version.py development <next-version>` on its
own reviewed development PR. Manual sweeps of package versions or core
requirements are unsupported.

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

The reviewed source definitions for `main` and `develop` live in
`.github/rulesets/` so the intended enforced configuration is reviewable here
and not only in GitHub settings. The ADR 0092 audit found no active GitHub
rulesets; Blandskron applies these reviewed definitions after the governance PR
is approved. `.github/rulesets/protect-release-tags.json` additionally defines
immutable `v*` tags (no update, no force-update or deletion) without
restricting creation, because the approved release workflow run is the only
thing that creates one (ADR 0082).

Once applied, both branches enforce:

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

### Required human approval

The versioned ruleset definitions set `required_approving_review_count` to
`1`, dismiss stale approvals after every push and require approval of the last
push. Agents request that review from Blandskron. GitHub rulesets cannot name
one reviewer, so the request and formal review provide that accountability.

During the ADR 0092 audit GitHub returned no active rulesets; the reviewed
definitions in `.github/rulesets/` must be imported or updated by the
maintainer after this PR is approved. This policy does not silently change
GitHub settings.

### No bypass actors

`bypass_actors` is empty, so no one pushes past the rules silently. An admin
can still edit or disable a ruleset in settings for a genuine emergency,
which is visible and auditable in a way a per-push bypass is not.

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
- leave preliminary review comments or request changes;
- create release/hotfix branches when separately authorized;
- update backlog/documentation;
- create ADRs/RFCs;
- open follow-up Issues.

It must not:

- approve its own PR;
- substitute an agent review for Blandskron's required formal review;
- merge an agent-authored PR;
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
