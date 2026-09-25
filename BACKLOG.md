# Backlog

This file tracks current and future work. GitHub Issues own executable tasks;
completed work remains available through Git history and closed Issues. The
[maturity matrix](docs/MATURITY.md) describes shipped behavior.

## In progress

- [~] [#512](https://github.com/Blandskron/agnara/issues/512): establish the
  1.0.3 documentation and synchronized package metadata baseline. Acceptance:
  no runtime or public API change; current docs, links and packaging checks pass.

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
