# Backlog

This file tracks active and future work. GitHub Issues own executable tasks;
completed work and review evidence remain in closed Issues, merged PRs and Git
history. The [maturity matrix](docs/MATURITY.md) describes implemented behavior.
Do not accumulate completed-task chronology in this file.

## Future work requiring a scoped Issue and review

- [ ] Maintain runnable tutorials and reference applications against the
  governed public API.
- [ ] Extend interoperability evidence only where the existing host contract
  applies; distinguish fixtures from supported integrations.
- [ ] Research Python 3.15 compatibility under
  [the research plan](docs/research/python-315-readiness.md) before changing the
  declared Python floor or CI support.
- [ ] Define scoped RFCs for the unimplemented Events adapter, further
  protocol projections and durable execution. Reserved distributions are not
  completed adapters; this entry alone authorizes no runtime implementation.

## Maintenance

- [~] Propose the opt-in host disconnect policy and scope its implementation,
  backed by an isolated receive-ownership/cancellation experiment (ADR 0100,
  #709). Keep the current adapter default unchanged.
- [ ] After maintainer review of ADR 0100, scope an application-owned recipe
  and exact installed-wheel/host evidence before any public API or support
  promotion.

Keep security fixes, dependency updates, documentation drift, supply-chain
checks and CI failures in normal issue/branch/PR review. When behavior changes,
remove superseded active guidance and repair navigation instead of appending
another competing description. Preserve necessary decision and release evidence;
age alone does not make a contract obsolete.
