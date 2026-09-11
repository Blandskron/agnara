# Roadmap

## Publication baseline

`0.1.0a8` is the sole retained publication baseline. It validates the reviewed
seven-distribution publication workflow. It is not a compatibility promise and
does not define the future product scope.

## One destination: 1.0.0

The next planned release is `1.0.0`. The project will not create another interim
publication. Work is selected by the architecture it
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

<<<<<<< HEAD
### DONE — 0.1.0a4, Application Boundaries

Closed. Its question — can Agnara be consumed as a framework from outside this
repository? — was answered by the unified exposure model (ADR 0070), the public
HTTP composition surface (ADR 0071) and the HTTP request surface, all validated
against a clean-room external consumer.

Its *publication* did not close. One of fourteen artifacts reached PyPI; the
rest were rejected before upload. `0.1.0a4` is superseded by `0.1.0a5` and
should not be installed. ADR 0078.

### ABORTED — 0.1.0a5, Publication Recovery

The immutable `v0.1.0a5` tag exercised the corrected preflight. Publication
readiness stopped the workflow before the first upload because the seven
Trusted Publishers were still unverified. No `0.1.0a5` artifact was published.

### ABORTED — 0.1.0a6, Publication Recovery

The immutable `v0.1.0a6` tag reached the publication job, but PyPI rejected
the first upload, `agnara-a2a`, because no Pending Trusted Publisher matched
that canonical project name and the workflow's OIDC identity. No A6 artifact
was published.

### ABORTED — 0.1.0a7, Publication and Security Recovery

The immutable `v0.1.0a7` tag was created while the publication record was
still `UNVERIFIED`, and publication readiness stopped the workflow before its
first upload. It fixed the three release-blocking CodeQL findings, which
remain fixed. No A7 artifact was published.

### NOW — 0.1.0a8, Release Pipeline Recovery

Current baseline target, and deliberately small. It carries the `0.1.0a7`
runtime unchanged and asks one question: can a release no longer consume a
version before every gate and a human have said yes? ADR 0082.

- **The tag is a consequence of the release, not its trigger.** A release is
  a `workflow_dispatch` run from `main`; every gate runs first, a reviewer
  approves in the protected `pypi` environment, and only that run creates the
  annotated tag, publishes, verifies and announces.
- **The human gate is verified by the pipeline.** A `pypi` environment without
  required reviewers refuses the release before anything is built.
- **`publication.json` records registry facts**, read back by a human after
  the last registry failure; the per-release authorization is the environment
  approval.
- Everything A5 to A7 got right stays: publish readiness as a separate claim
  (ADR 0079), kernel published last, post-publication verification gating the
  GitHub Release, one source of truth for the seven distributions, a
  SHA-pinned publication path.

### NEXT — 0.1.0a9, Execution Semantics

Unchanged in content; moved one release later by ADR 0082 after ADR 0081. Its
one question: does execution have streaming, identity and a measured cost?

- **Streaming model** — `I2`, which still blocks the most other work.
- **Execution identity and idempotency behaviour.**
- **Performance budgets** — `I14`.

### BETA — 0.1.0b1, Interoperability

Its one question: can the Python ecosystem use Agnara, and Agnara use it?

- **Framework and ecosystem interoperability** — `I20`. Agnara standalone, as
  a host, embedded inside an existing framework, and side by side. RFC 0008
  states the questions and decides none of them.
- **Security program** — `I10`. Threat model, invariants with tests, supply
  chain.
- **A2A, events, audit, composition and testing utilities** — `I4`, `I5`,
  `I8`, `I12`, `I17`.
- **Durable execution** — `I6`, the abstraction rather than the workers.

### RC — 0.1.0rc1

No new subsystems. Regressions, documentation, compatibility, security,
packaging and release validation only.

### 1.0

- Stable execution, DI, policy, failure and introspection models.
- Stable HTTP composition API and MCP projection.
- Public API governance and deprecation policy in force.
  `docs/PUBLIC_API.md` owns the governed surface.
- **Free-threaded Python** verification — `I15`.

### POST-1.0

Distributed workers, a plugin and extension model (`I13`), workflow
orchestration (`I11`), multi-tenancy and federation (`I16`), and further
protocol adapters.

## What Agnara is not becoming

An ORM, a broker, a scheduler, a worker runtime, a frontend framework, an
admin UI, or an LLM framework. `docs/TARGET_ARCHITECTURE.md` section 7 records
why for each.

Agnara does not replace the ecosystem, so it has to be able to work with it
— alone, embedded, alongside, integrated.

## The governing trade

When features and architecture conflict, architecture wins. When a proprietary
mechanism and an open standard both work, the standard wins. When convenient
coupling and a clean boundary conflict, the boundary wins. When a large core
and a small kernel with strong adapters both work, the kernel stays small.
=======
## Non-goals

Agnara is not becoming an ORM, broker, scheduler, worker runtime, frontend
framework, admin UI or LLM framework. The kernel remains capability-first,
transport-neutral and small; adapters evolve around it.
>>>>>>> 15cdde3ccb0211665dc88e153872be1acdeee5aa
