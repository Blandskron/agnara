# Roadmap

## Publication baseline

`0.1.0a8` is the sole retained publication baseline. It validates the reviewed
seven-distribution publication workflow. It is not a compatibility promise and
does not define the future product scope.

## One destination: 1.0.0

The next planned release is `1.0.0`. The project will not create another alpha,
beta or release-candidate publication. Work is selected by the architecture it
stabilizes, not by a pre-release cadence.

`docs/releases/RELEASE_PLAN.md` defines the evidence required to publish 1.0.0;
`docs/INITIATIVES.md` defines dependency order; `BACKLOG.md` holds ready work.

## Required product outcomes

- Execution semantics: streaming, execution identity and operational
  idempotency are designed, implemented and tested.
- Performance: compiled paths have budgets and CI detects regressions.
- Interoperability: Agnara works standalone, as a host, embedded and
  side-by-side without coupling the kernel to a framework.
- Security: the threat model, supply-chain controls and security invariants
  have current evidence.
- Public API: the supported surface and migration commitments are stable.
- Documentation: applications can be built from supported documentation alone.

## Non-goals

Agnara is not becoming an ORM, broker, scheduler, worker runtime, frontend
framework, admin UI or LLM framework. The kernel remains capability-first,
transport-neutral and small; adapters evolve around it.
