# Backlog

This file tracks current and future work. GitHub Issues own executable tasks;
completed work remains available through Git history and closed Issues. The
[maturity matrix](docs/MATURITY.md) describes shipped behavior.

## In progress

- [~] [#518](https://github.com/Blandskron/agnara/issues/518): add a runnable
  public-API nested invocation guide with parent/child authorization tests.
  Acceptance: standalone example, linked guide and required quality gates pass.
  Implementation is ready for review; the full local gate also encounters the
  pre-existing release-state inconsistency tracked in
  [#519](https://github.com/Blandskron/agnara/issues/519).

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
