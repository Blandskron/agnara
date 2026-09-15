# ADR 0092 — Agent Authorship and Human Maintainer Review

- Status: Accepted
- Date: 2026-09-15
- Tracking: GitHub Issue #407
- Related: ADR 0015, ADR 0016, ADR 0019

## Context

ADR 0019 recorded a cautious, historical co-author model while Agnara had no
settled separation between an agent's implementation and a maintainer's review.
The repository now has verified agent identities in
`.github/ai-agent-identities.toml`, and its owner has chosen an explicit
agent-authorship plus human-review workflow. Leaving the old default active
would make Git history falsely attribute agent-written work to the maintainer.

## Decision

### D1 — An implementing agent is the primary commit author

When an agent materially writes a commit, it must use its exact registered
`git_name` and `email` as that commit's author. It is not represented merely
by a `Co-authored-by` trailer. The agent verifies the committed author and
message before push. A human maintainer is neither author nor co-author of
agent-written work unless the maintainer materially implements part of that
specific commit and explicitly asks to be credited.

When several agents materially contribute, prefer separate, accurately
authored commits over blanket trailers. Never invent an identity, add a
non-participating agent, create empty commits or split trivial changes merely
to alter contribution statistics.

### D2 — Blandskron is the maintainer and formal reviewer

Blandskron is repository owner, maintainer, architecture/governance decision
maker and merge authority. His normal contribution to an agent-authored change
is a formal GitHub Pull Request review, not implementation authorship.

An implementation agent opens or prepares a PR to `develop`, requests review
from `Blandskron`, and leaves it unmerged. A conversation comment or a
self-review is supplementary evidence only; it never replaces GitHub's formal
`Approve`, `Request changes`, or `Comment` review flow. Agents never approve
or merge their own PRs.

### D3 — Preserve truthful attribution through merge

Before merging, the maintainer verifies that the selected GitHub merge method
preserves the verified implementation author. A merge commit preserves the
agent-authored branch commit. Squash is allowed only when its resulting author
metadata is verified to remain the implementing agent; it must not silently
turn Blandskron into the implementation author. Historical commits and ADRs
are not rewritten to conform to this prospective rule.

### D4 — Platform limitations are explicit

An agent should create the PR using its own GitHub/App identity where the
platform supports it. If an available authenticated client instead creates it
under another account, the PR records that limitation; no identity is faked.
Repository rules can require an approval but cannot name a particular reviewer,
so the PR request and formal review identify Blandskron.

## Consequences

- Git commits accurately separate agent implementation from human review.
- Agent-authored PRs wait for a human decision even when CI is green.
- The versioned ruleset definitions require one approval and re-review after
  a push; the maintainer applies them in GitHub settings after reviewing the
  governance PR.
- Older co-author records remain historical evidence only. ADR 0092 governs
  current active contributor workflow documents.
