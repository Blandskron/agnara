# Backlog

GitHub Issues are executable work units. Closed Issues, merged PRs and Git
retain completed work and review evidence. See the [roadmap](ROADMAP.md) for
the milestone and the [maturity matrix](docs/MATURITY.md) for current behavior.

## November 14 presentation

Scope each work item in an Issue before implementation. Priorities reflect
what improves the demonstration and adoption within the available time.

- [ ] **P1 · Demo freeze.** Select a reviewed commit, rerun the stable
  rehearsal from installed wheels and record the exact commit, package versions
  and commands as described in the [roadmap](ROADMAP.md).

## After the presentation

- [ ] Maintain runnable tutorials, reference applications and interoperability
  evidence against the governed API and explicit host contract.
- [ ] Scope runtime CLI diagnostics from the clean-project rehearsal.
- [ ] Review the [Events feasibility case](docs/rfc/0011-event-initial-projection.md#first-feasibility-case-inventory-snapshot).
  If accepted, scope EVT-01 in its own Issue before selecting a broker and
  running the isolated experiment.
- [ ] Evaluate [durable execution](docs/rfc/0012-durable-execution-boundary.md)
  and further protocol projections in separate feasibility Issues.
- [ ] Review activation of the
  [Python 3.15 research plan](docs/research/python-315-readiness.md) before
  changing the Python floor or CI support.

Handle regressions, security fixes, dependency updates and CI failures through
normal Issue and PR review. Preserve decision and release evidence when
removing superseded guidance.
