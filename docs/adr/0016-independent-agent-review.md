# ADR 0016 — Independent Agent Review

- Status: Proposed

## Decision

Independent review is the preferred autonomous governance model.

Where two GitHub identities are available:

```text
Implementation Agent != Review Agent
```

The review agent may approve or request changes.

Where only one identity is available, required peer approvals must not be configured in a way that deadlocks autonomous operation.

The single agent performs mandatory self-review but cannot label it as independent approval.

## Rationale

Autonomy does not justify fabricated peer review.

The repository should accurately represent the strength of its review process.

## Future

High-risk paths may later require independent agent or human/code-owner approval through repository rulesets.
