# Backlog

This file tracks current and future work. GitHub Issues own executable tasks;
completed work remains available through Git history and closed Issues. The
[maturity matrix](docs/MATURITY.md) describes shipped behavior.

## In progress

- [x] [#571](https://github.com/Blandskron/agnara/issues/571): runnable Starlette
  embedding guide with host identity, input/outcome mapping and owned resources.
  Concurrency/cancellation/exceptional-exit tests and local gates pass;
  implementation awaits formal maintainer review and merge.

The installed-wheel host correction from #569 was merged by PR #570; its Issue
closed after all required CI passed. Review identity remains covered by #524.

The persistence loop correction from #565 was merged by PR #568; its Issue
closed after all required CI passed. The recorded review identity remains
subject to governance Issue #524.

Dependabot PR #567 was closed as redundant: its action pins already match
the updates integrated by #525. The reviewed `develop` target configuration
still awaits normal maintainer-controlled promotion to the default branch.

The SQLite persistence guide from #564 was merged by PR #566; its Issue closed
after all required CI passed.

The FastAPI embedding guide from #562 was merged by PR #563; its Issue closed
after all required CI passed.

The read-only local documentation MCP from #559 was merged by PR #561; its
Issue closed after all required CI passed.

The discovery, selection and implementation path from #558 was merged by
PR #560; its Issue closed after all required CI passed.

The community policies from #556 were merged by PR #557; its Issue closed
after all required CI passed.

The Litestar lifespan correction from #554 was merged by PR #555; its Issue
closed after required CI passed.

The schema contracts guide from #552 was merged by PR #553; its Issue closed
after required CI passed.

The dependency lifecycle guide from #550 was merged by PR #551; its Issue
closed after required CI passed.

The telemetry guide from #548 was merged by PR #549; its Issue closed after
required CI passed.

The deadline and cancellation guide from #546 was merged by PR #547; its Issue
closed after required CI passed.

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
