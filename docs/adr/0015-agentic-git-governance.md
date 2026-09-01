# ADR 0015 — Agentic Git Governance

- Status: Proposed

## Decision

Agnara development uses an Issue-driven Pull Request workflow.

Normal unit:

```text
BACKLOG item
→ GitHub Issue
→ short-lived branch
→ PR
→ review
→ merge
```

`main` and `develop` are protected long-lived branches.

## Rationale

The project is intended to be operated substantially by AI agents.

Agent autonomy requires more traceability, not less.

GitHub artifacts provide persistent state understandable by humans and other agents.

## Consequences

- no normal direct pushes to `main` or `develop`;
- one Issue / branch / PR is the default;
- agents inspect pending PRs/Issues before selecting new work;
- CI is a merge gate;
- discovered out-of-scope work becomes a new Issue;
- release/hotfix flows are explicit.

## Review constraint

A PR author cannot provide the independent approval for its own PR.

Agnara therefore distinguishes:

1. dual-agent mode with separate implementer/reviewer identities;
2. single-agent mode with PR + CI + documented self-review and no fake approval.

See `GIT_WORKFLOW.md`.
