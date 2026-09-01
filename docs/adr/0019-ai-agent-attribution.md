# ADR 0019 — Evidence-Based AI-Agent Attribution

- Status: Proposed
- Date: 2026-08-31
- Tracking: GitHub Issue #12

## Context

Agnara expects AI agents to implement and review work through the same
auditable GitHub workflow as human contributors. The repository already has
historical commits containing AI co-author trailers, but it has no
repository-owned identity registry and no documented evidence that every
historical address maps to an authorized GitHub account.

Model names, product names, runtime sessions and logical roles are not GitHub
identities. Treating them as interchangeable can fabricate credit, hide the
human directing a change, or cause legitimate attribution to disappear during
a squash merge.

The policy must improve prospective traceability without rewriting accepted
history or collecting private identity data.

## Decision

### Evidence hierarchy

Agnara records contribution in two complementary places:

1. Git commit authorship and valid trailers are the source of truth for
   accepted authorship.
2. Issues, PR bodies, comments and reviews record operating roles, material
   contributions, review work and identity-verification limitations.

An exact agent identity is considered eligible for Git-native attribution
only when:

- the agent materially participated as an author;
- a repository maintainer has authorized that identity for Agnara; and
- authoritative GitHub evidence maps the exact email to the stated user or
  bot account.

A model/provider label, an unverified email, a public-search guess or a past
trailer by itself does not satisfy this standard.

### Human-directed work

The directing human remains the primary commit author. A materially
contributing agent may be added with:

```text
Co-authored-by: Exact Verified Name <exact-verified-email>
```

only when the evidence hierarchy is satisfied. The trailer appears at the end
of the message after a blank line. The primary author is not repeated as a
co-author.

### Autonomous bot work

A fully autonomous bot with its own verified, authorized GitHub identity may
be the primary author. It must use that identity directly and must not
impersonate a human or add itself again as a co-author.

### Roles and review

Only agents that actually participated are recorded. No agent may attribute a
different agent without evidence of its contribution.

Implementation authorship and review are distinct. A review-only agent is
credited through a GitHub review or PR comment and is not normally a
co-author. If a reviewer also makes a material implementation contribution,
the PR distinguishes both roles and applies the same identity-verification
rule.

An agent without a verified GitHub identity is documented in the Issue or PR:

```text
Agent: <name used in the session>
Role: <logical role>
Contribution: <material work performed>
Identity verified for GitHub attribution: no
Co-authored-by trailers included: none
Non-verifiable agents documented: <name>
```

It receives no guessed trailer.

### Commit and squash integrity

Before push, the contributor inspects the committed author and parsed
trailers. Amend and rebase operations preserve every legitimate trailer.

Before squash merge, the merger constructs and inspects the final commit
message explicitly. GitHub is not assumed to copy trailers from every branch
commit. Legitimate trailers are carried into the squash body after a blank
line, while duplicates and unsupported trailers are removed. After merge, the
accepted commit is inspected again.

### Existing history

This decision is prospective. Agnara does not rewrite published history or
mass-add/remove attribution solely to apply this policy. Historical trailers
remain historical evidence, not automatic authorization for future use.

### Registry and contributor files

Agnara will not create an agent-identity registry yet. The audit for Issue #12
found no repository-configured, verified AI-agent identity to register. An
empty registry adds ceremony without enforcement value, while a guessed entry
would violate this decision.

When a maintainer authorizes the first independently verifiable agent account,
a follow-up Issue may add a minimal machine-readable registry containing only
public attribution data and evidence references—never credentials, tokens or
private email addresses.

A separate `AI_CONTRIBUTORS` file is also rejected. It would duplicate Git
history and PR evidence and would drift unless maintained manually.

## Consequences

Positive:

- humans and agents can distinguish authorship, implementation and review;
- non-verifiable agent work remains transparent without fabricated identity;
- squash merges preserve deliberate credit;
- no private credentials or ambiguous identity guesses enter the repository;
- historical Git data remains stable.

Negative:

- attribution verification remains a manual review gate until a trusted
  registry exists;
- non-verifiable agents receive role credit in GitHub artifacts but not
  Git-native co-author linkage;
- mergers must inspect and sometimes construct squash messages explicitly.

## Guardrails

- never invent an agent name/email pair for a commit;
- never treat a model or provider domain as proof of account ownership;
- never attribute an agent that did not participate;
- never use `Co-authored-by` as a substitute for review evidence;
- never duplicate the primary author in trailers;
- never discard legitimate trailers silently during history editing or merge;
- never store secrets or private identity evidence in a registry;
- never rewrite published history merely to normalize attribution.

## Revisit when

- an authorized AI agent has an independently verifiable GitHub account;
- GitHub exposes stronger machine-readable co-author verification;
- repeated attribution mistakes justify trusted automated enforcement;
- project governance adopts signed commits or a contributor identity system.
