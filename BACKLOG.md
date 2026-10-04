# Backlog

This file tracks current and future work. GitHub Issues own executable tasks;
completed work remains available through Git history and closed Issues. The
[maturity matrix](docs/MATURITY.md) describes shipped behavior.

## In progress

- [~] [#546](https://github.com/Blandskron/agnara/issues/546): add a runnable
  direct invocation deadline and cancellation guide. Acceptance: absolute
  monotonic deadlines, canonical timeout, propagated caller cancellation,
  scope denial before effects, owned tasks and resource cleanup, public imports,
  outside-checkout execution and required CI pass.

The filtered introspection guide from #543 and routing property fixture repair
from #544 were merged by PR #545; both Issues closed after required CI passed.

The official-client MCP tools guide from #541 was merged by PR #542 and its
Issue closed after the required CI passed.

The confirmation guide from #539 was merged by PR #540 and its Issue closed
after the required CI passed.

The HTTP SSE lifecycle guide from #537 was merged by PR #538 and its Issue
closed after the required CI passed.

The current-contract documentation from #507 was merged by PR #536 and its
Issue closed after the required CI passed.

The JSON numeric Literal fix from #533 was merged by PR #534 and its Issue
closed after the required CI passed.

The enum input contract fix from #531 was merged by PR #532 and its Issue
closed after the required CI passed.

The float input range fix from #529 was merged by PR #530 and its Issue closed
after the required CI passed.

The action updates from #528 were merged by PR #525 and its Issue closed after
the required CI passed. Dependabot's new target configuration takes effect
when it is promoted to `main` through the reviewed workflow.

The edge publication guard from #526 was merged by PR #527 and its Issue
closed after the required CI passed.

The runnable direct-idempotency guide from #522 was merged by PR #523 and its
Issue closed after the required CI passed.

The published 1.0.3 record from #519 was merged by PR #521; the Issue closed
after required CI passed.

The runnable nested invocation guide from #518 was merged by PR #520 and its
Issue closed after the required CI passed.

The documentation baseline from #512 was integrated by PR #513; release
tooling prose from #515 was integrated by PR #516. Publication is separate
from these completed development tasks.

## Future work requiring a scoped Issue and review

- [ ] Maintain runnable tutorials and reference applications against the
  governed public API.
- [ ] Extend interoperability evidence only where the existing host contract
  applies; distinguish fixtures from supported integrations.
- [ ] Research Python 3.15 compatibility under
  [the research plan](docs/research/python-315-readiness.md) before changing the
  declared Python floor or CI support.
- [ ] Evaluate additional protocol projections, durable execution and reserved
  distributions through separate RFCs. No runtime implementation is authorized
  by this backlog entry alone.

## Maintenance

Keep security fixes, dependency updates, documentation drift, supply-chain
checks and CI failures in normal issue/branch/PR review. Do not use roadmap
headings as evidence that a feature ships.
