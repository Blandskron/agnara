# Roadmap

The current stable product is Agnara 1.x. [Maturity](docs/MATURITY.md) records
what exists; [backlog](BACKLOG.md) records actionable work; the
[1.0 release evidence](docs/releases/v1.0.0.md) is historical. This roadmap is
a design horizon. `2.x` names a strategic program, not a SemVer commitment:
features may ship in compatible 1.x releases when their contracts and quality
gates permit.

## Near term: maintain the 1.x contract

Keep the seven-distribution publication path reliable, fix security and
correctness defects, and maintain the documented public API. Python 3.15
readiness is a separate compatibility program with its own activation and
evidence rules in [the research plan](docs/research/python-315-readiness.md).
It does not imply raising the Python 3.14 minimum or claiming free-threading
support.

## Strategic platform program

These are provisional design programs, not implemented features or a package
creation checklist. Each requires an RFC/ADR, trust-boundary analysis,
conformance evidence and a separate executable issue before implementation.
Potential independent package boundaries include `agnara-data`,
`agnara-tasks`, `agnara-realtime`, `agnara-auth`, `agnara-files`,
`agnara-cache`, `agnara-workflows` and `agnara-ui`. These names are examples,
not approved distributions. Existing `agnara-http`, `agnara-mcp`,
`agnara-a2a` and `agnara-events` have the maturity recorded in
[MATURITY.md](docs/MATURITY.md).

| Program | Question to settle | Dependency |
| --- | --- | --- |
| U1 — Universal Application Graph | How can one versioned, redacted machine-readable graph extend today's introspection? | Existing capability, app and exposure model |
| U2 — Data | Which Entity, Store, Query, Repository, Transaction and Migration contracts belong to Agnara? | U1 identity and schema boundaries |
| U3 — Tasks | How can execution be detached and durable without confusing a task with a capability? | Execution identity, idempotency and U1 |
| U4 — Events and realtime | How are facts published and live subscriptions represented without choosing a broker? | U1, delivery and trust semantics |
| U5 — Native A2A | What should the reserved adapter actually project, and with what authority? | Capability discovery, identity and protocol review |
| U6 — Workflows | How are multiple capabilities and durable steps coordinated without duplicating task semantics? | U3, U4 and composition |
| U7 — Agent-native development | How can agents inspect impact, policy and verification evidence safely? | U1 and visibility controls |
| U8 — Declarative UI | Can Page, Component, Layout, Form, Table, State, Action and Navigation be expressed portably? | U1 and authorization-aware data/actions |
| U9 — Identity and tenancy | Which identity and isolation contracts are portable across hosts? | Existing principal/policy boundary; U2–U6 threat models |
| U10 — Deployment | Which graph parts can map to local, process, service and distributed topologies? | U1 and runtime contracts |

The order may change when design evidence reveals a different dependency.
Data contracts should not lock in an ORM; event contracts should not lock in a
broker; UI work remains **RESEARCH** until an ADR and implementation evidence
exist. Possible UI progression is SSR, progressive enhancement, interactive
components and realtime. No frontend-framework replacement is claimed today.

The conceptual boundaries are: **Capability** is what the system can do;
**Task** is detached or durable execution; **Event** is a fact that occurred;
**Workflow** coordinates steps; **Agent** is an autonomous actor using
capabilities under policy. These future definitions are provisional.

## U1: Universal Application Graph

Today's frozen introspection snapshot describes projects, apps, capabilities,
exposures, dependencies and selected metadata after visibility filtering. U1
would evolve that snapshot into a versioned, machine-readable application
graph. Candidate nodes include Project, Apps, Capabilities, Models, Resources,
Stores, Dependencies, Policies, Effects, Events, Tasks, Workflows, Agents,
Interfaces, Exposures, Deployments and Infrastructure. Most of these are not
current descriptors. Sensitive values and private topology must be redacted
before serialization. Agents should be able to inspect relationships without
reconstructing them from scattered source files; graph identity, versioning,
visibility and provenance need their own design.

## U7: Agent-native development

| Interface | Current status | Boundary |
| --- | --- | --- |
| `agnara inspect`, `agnara graph`, `agnara context` | **IMPLEMENTED** | Current discovery/context views; see `docs/CLI_SPEC.md`. |
| `agnara agent context`, `agnara agent impact`, `agnara agent verify` | **RESEARCH** | Conceptual names only; no commands or impact/verification engine exist. |

The research goal is for an agent to ask which capabilities exist, how they
depend on each other, what effects and policies apply, which surfaces expose
them, which components a change affects and which tests verify them. The
answers must respect discovery visibility and be backed by reproducible
evidence. A planned command becomes **PLANNED** only after its contract is
accepted; the table does not preauthorize implementation.

See [architecture](ARCHITECTURE.md) for the core/platform boundary and
[vision](VISION.md) for the product goal.
