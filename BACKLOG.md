# Backlog

GitHub Issues are executable work units. Closed Issues, merged PRs and Git
retain completed work and review evidence. See the [roadmap](ROADMAP.md) for
the milestone and the [maturity matrix](docs/MATURITY.md) for current behavior.

## November 14 presentation

Scope each work item in an Issue before implementation. Priorities reflect
what improves the demonstration and adoption within the available time.

- [ ] **P0 · MCP transport evidence.** Use one host-owned SDK transport and
  record exact versions. Exercise startup, discovery, invocation, denial
  before effects, caller cancellation and resource shutdown. Keep the
  existing in-process flow as the demo fallback.
- [ ] **P1 · CLI adoption.** Rehearse scaffolding, inspection and the existing
  static `doctor` from a clean environment. Document one reproducible path and
  record the first runtime diagnostic gap for a separate Issue.
- [ ] **P1 · A2A scope decision.** Record what the provisional complete-result
  profile can demonstrate with the pinned client and host. Review API stability
  and broader host support separately from the runnable recipe.
- [ ] **P1 · Core, HTTP and telemetry rehearsal.** Use the same capability for
  direct, HTTP and MCP calls. Verify canonical results, denial before effects,
  resource closure and trace redaction. Record the candidate-wheel commit,
  versions and commands used at the demo freeze.
- [ ] **P2 · Events feasibility.** Identify one first use case and its minimum
  contract in the [Events proposal](docs/rfc/0011-event-initial-projection.md).
  Capture a proceed or defer decision for follow-up review.

## After the presentation

- [ ] Maintain runnable tutorials, reference applications and interoperability
  evidence against the governed API and explicit host contract.
- [ ] Scope runtime CLI diagnostics from the clean-project rehearsal.
- [ ] Evaluate [durable execution](docs/rfc/0012-durable-execution-boundary.md)
  and further protocol projections in separate feasibility Issues.
- [ ] Review activation of the
  [Python 3.15 research plan](docs/research/python-315-readiness.md) before
  changing the Python floor or CI support.

Handle regressions, security fixes, dependency updates and CI failures through
normal Issue and PR review. Preserve decision and release evidence when
removing superseded guidance.
