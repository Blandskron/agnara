# Agnara

> **Capability-native Python for the agentic era.**

Agnara is a Python 3.14-native capability framework for building services that can be consumed by humans, applications, services, and AI agents without making HTTP the center of the architecture.

Agnara starts from a simple premise:

> **Business capabilities are the product. Protocols are adapters.**

A capability is defined once and may later be exposed through HTTP, MCP, A2A, events, tasks, CLI, internal calls, or future transports without duplicating domain logic.

## Install

```bash
pip install agnara==0.1.0a3
```

Or track the newest pre-release:

```bash
pip install --pre agnara
```

Requires CPython 3.14 or newer. The core distribution has no third-party
dependencies.

`0.1.0a3` is the last release that published completely, and it publishes the
`agnara` core kernel only. `0.1.0a4` was tagged and published *partially* — one
of its fourteen artifacts reached PyPI — so it is superseded and should not be
installed. The `v0.1.0a5` and `v0.1.0a7` attempts stopped before their first
upload because publication readiness found unverified Trusted Publishers;
`0.1.0a6` failed on the first PyPI upload because the `agnara-a2a` Pending
Trusted Publisher did not match. All four were tagged before their gates ran.
`0.1.0a8` is the next candidate for all seven synchronized distributions, and
the first whose tag can only be created by an approved, fully gated workflow
run; until it is published and verified, the six adapter names are not on the
public index.

## What the 0.1.0a8 candidate adds

`0.1.0a8` carries the `0.1.0a7` runtime unchanged and replaces the release
flow that burned four versions, so what it adds to a *user* is the `0.1.0a4`
application alpha, actually published: an external consumer can install the
built artifacts as ordinary dependencies and compose direct, HTTP and MCP
surfaces without private imports or monkey patches, over the public HTTP
composition API, governed public surfaces for every distribution, consistent
JSON schema materialization across transports, and strengthened policy, failure
and observability conformance.

See the [`0.1.0a8` release notes](docs/releases/v0.1.0a8.md) for the current
recovery candidate, the [`0.1.0a7` notes](docs/releases/v0.1.0a7.md) for the
last aborted attempt, and the
[`0.1.0a4` notes](docs/releases/v0.1.0a4.md) for what the implementation does,
and the [a3-to-a4 migration guide](docs/releases/v0.1.0a4.md#migration-guide),
which is the one that applies. The install command above resolves `0.1.0a4`
today; pin `0.1.0a3`, or wait for `0.1.0a8`, until the release completes.

## Quick start

```python
import asyncio

from agnara import Agnara, Risk, StandardEffect
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    invoke_result,
)
from agnara.policy import Principal

app = Agnara("billing")


@app.capability(
    description="Refund a captured payment.",
    scopes=("billing:write",),
    effects=(StandardEffect.FINANCIAL_WRITE,),
    risk=Risk.HIGH,
)
def refund(payment_id: str, amount_cents: int) -> str:
    return f"refunded {amount_cents} cents for {payment_id}"


async def main() -> None:
    capabilities = app.compile()
    dependencies = DIRegistry()
    plan = ExecutionPlan.compile(capabilities["billing.refund"], dependencies)

    outcome = await invoke_result(
        plan,
        ExecutionContext(
            Invocation(
                capability_id=plan.definition.id,
                payload={"payment_id": "pay_123", "amount_cents": 2500},
                metadata={},
            ),
            DIContainer(dependencies),
            principal=Principal("quickstart", scopes={"billing:write"}),
        ),
    )
    print(outcome)


asyncio.run(main())
```

The capability is declared once, with its risk and effects, and invoked
directly — no server, no HTTP, no transport. `examples/quickstart.py` in this
repository is the longer version, including dependency injection and canonical
failure handling.

## Why Agnara exists

Most Python web frameworks were created for a world centered on HTTP APIs, REST, request/response cycles, and human developers. The software landscape now includes AI agents, MCP, A2A, long-running tasks, event-driven systems, human approval flows, machine-readable discovery, and agent-oriented security.

Agnara is not intended to retrofit those concepts onto an HTTP-first architecture.

It is intended to begin from them.

## Design thesis

Traditional framework:

```text
Python function
      ↓
HTTP route
      ↓
OpenAPI
```

Agnara:

```text
                       HTTP
                        │
                        ▼
MCP ───────────────► Capability ◄────────────── A2A
                        ▲
                        │
                 Events / Tasks
                        │
                        ▼
                  Python handler
```

The protocol is not the application model.

The capability graph is.

## Core principles

1. Capability-first, not route-first.
2. Transport-neutral business logic.
3. Python 3.14 as the minimum runtime baseline.
4. Modern typing as the source of truth.
5. Compile execution plans at startup.
6. Agents are first-class API consumers.
7. Human and agent authorization are first-class concerns.
8. Side effects, risk, idempotency, cost, and interaction requirements are machine-readable.
9. Observability is part of the execution model.
10. Small core, replaceable adapters, standards over proprietary protocols.
11. No LLM provider belongs in the core.
12. Performance claims must be reproducible.

## Target developer experience (design, not current API)

```python
from agnara import Agnara

app = Agnara("commerce")


@app.capability
async def get_product(product_id: int) -> Product:
    return await products.get(product_id)


app.expose(get_product).http.get("/products/{product_id}")
app.expose(get_product).mcp.tool()
app.expose(get_product).a2a.skill()
```

One capability.

One dependency graph.

One security policy.

One telemetry model.

Multiple protocol surfaces.

## Security-aware capabilities (design sketch)

```python
@app.capability(
    scopes={"payments:create"},
    effects={"financial-write"},
    risk="high",
    confirmation="required",
    idempotent=False,
)
async def send_payment(
    command: PaymentCommand,
    ctx: Context,
) -> PaymentReceipt:
    ...
```

Agnara should make enough semantics machine-readable for a client or agent to determine whether an operation is safe to invoke automatically.

## Architectural layers

```text
Application
    │
    ▼
Capability Registry
    │
    ├── Schema Engine
    ├── Dependency Graph
    ├── Policy Engine
    └── Discovery Metadata
    │
    ▼
Execution Plan Compiler
    │
    ▼
Execution Runtime
    │
    ├── HTTP Adapter
    ├── MCP Adapter
    ├── A2A Adapter
    ├── Event Adapter
    ├── Task Adapter
    ├── CLI Adapter
    └── Internal Invocation
```

## Initial workspace

```text
agnara/
├── packages/
│   ├── agnara/
│   ├── agnara-http/
│   ├── agnara-mcp/
│   ├── agnara-a2a/
│   ├── agnara-events/
│   ├── agnara-telemetry/
│   └── agnara-cli/
├── tests/
│   ├── architecture/
│   ├── conformance/
│   ├── integration/
│   └── benchmarks/
├── docs/
│   ├── adr/
│   └── rfc/
├── AGENTS.md
├── ARCHITECTURE.md
├── BACKLOG.md
├── PRINCIPLES.md
├── ROADMAP.md
└── pyproject.toml
```

Not every package must be implemented in the first milestone. The structure defines boundaries before implementation pressure begins to blur them.

## Initial scope

The first meaningful release should prove:

```text
typed Python capability
        ↓
compiled execution plan
        ↓
direct invocation
        ↓
HTTP exposure
        ↓
OpenAPI generation
        ↓
MCP exposure
        ↓
consistent validation, policy and telemetry
```

A2A, event transports, distributed tasks, native/Rust acceleration, and broader plugin infrastructure follow only after this foundation is demonstrably correct.

## Non-goals

Agnara is not:

- an ORM;
- an LLM orchestration framework;
- a RAG framework;
- a vector database;
- a workflow product;
- a message broker;
- an authentication database;
- a replacement for MCP or A2A;
- a custom HTTP protocol;
- a custom AI model SDK.

Agnara integrates standards. It does not recreate them.

## Runtime baseline

Agnara targets CPython 3.14+.

The architecture must be safe under conventional CPython and designed consciously for free-threaded Python. Thread-safety cannot be assumed merely because historical CPython used a GIL.

## Project status

```text
Status:          Alpha (experimental)
Last complete:   v0.1.0a3 (PyPI, core distribution only)
Partial:         v0.1.0a4 (core wheel only; superseded, do not install)
Aborted:         v0.1.0a5, v0.1.0a6, v0.1.0a7 (nothing published)
Next candidate:  v0.1.0a8 (seven synchronized distributions)
```

`v0.1.0a3` is the last release that published completely, following `v0.1.0a2`,
which was the first version to reach PyPI. Neither is production-ready and the
public API may change without a deprecation cycle.

`v0.1.0a4` was tagged and its upload stopped after the first file, so PyPI
holds `agnara 0.1.0a4` as a wheel with no sdist and none of the six adapter
distributions. The tag and that file are historical and are not being rewritten;
`v0.1.0a5`, `v0.1.0a6` and `v0.1.0a7` published nothing and remain immutable;
`v0.1.0a8` is the candidate that publishes the full set, through a release
flow that creates the tag only after every gate and a human approval. ADR 0078
records A4, ADR 0079 the pipeline change, ADR 0080 and ADR 0081 the A5 to A7
recoveries, and ADR 0082 the dispatch-driven release.

The repository should not claim production readiness, benchmark leadership, security guarantees, or protocol conformance until those claims are backed by automated evidence.

See `CHANGELOG.md` for the released record and the exact published scope, and
`docs/MATURITY.md` for what each subsystem actually supports today. Several
sections below describe intended design rather than shipped behaviour and say
so; the maturity table is the authoritative answer when they are unclear.

## Documentation order for contributors and agents

Read in this order:

1. `VISION.md` — why Agnara exists
2. `PRINCIPLES.md` — the rules a decision must not break
3. `ARCHITECTURE.md` — how the system is structured today
4. `docs/MATURITY.md` — **what actually exists**, per subsystem
5. `docs/API_DESIGN.md`
6. `docs/TARGET_ARCHITECTURE.md` — where the structure is going, and the gaps
7. `docs/INITIATIVES.md` — what to build, in dependency order
8. `BACKLOG.md` — decomposed items ready to implement
9. `QUALITY_GATES.md`
10. `AGENTS.md`

`docs/DOCUMENTATION_MAP.md` records which document owns which kind of truth.
Before trusting a status you read anywhere else, check `docs/MATURITY.md`:
several subsystems in this README are described as designs rather than
shipped behaviour, and that file is the one that says which is which.

## Serving capabilities over HTTP

```python
from agnara_http import Binding, BindingSource, Http, OpenApiInfo

http = Http("public")
http.get("/orders/{order_id}", show_order, Binding("order_id", BindingSource.PATH))
asgi = http.compile(app.compile(), openapi=OpenApiInfo("Shop API", "1.0.0"))
```

`asgi` is an ASGI 3 application; hand it to any ASGI server. Seven public
names cover the whole surface, and `docs/HTTP_COMPOSITION.md` is the guide —
including what `0.1.0a4` does not expose yet. `examples/http_service.py` is a
runnable version.

`agnara-http` is not published on PyPI yet. It is part of the seven-package
`0.1.0a8` candidate and becomes installable from the public index only after
the authorized release publishes it.

## HTTP documentation and capability discovery

Agnara keeps familiar HTTP documentation without making it the semantic
center:

```text
Capabilities → HTTP exposures → OpenAPI 3.2 → replaceable documentation UI
```

Pinned Swagger UI, ReDoc and Scalar providers are optional consumers of
generated OpenAPI. They do not belong in `agnara-core`, and none is selected
as an unconditional default before the shared browser conformance gate.

The read-only Agnara Explorer uses a separate protocol-neutral introspection
snapshot so it can show apps, non-HTTP exposures, dependencies, policies,
effects, risk, idempotency and confirmation. Machine-readable discovery
remains available without parsing or enabling any HTML UI.

The design and security boundaries are specified in:

- `docs/adr/0018-replaceable-documentation-providers.md`
- `docs/REFERENCE_RESEARCH.md`

## License

Agnara is licensed under the [Apache License 2.0](LICENSE).

## Django-like modular apps, redesigned for 2026

Agnara adopts the productive project/app idea while changing what an app means.

```bash
agnara project create commerce

cd commerce

agnara app create users
agnara app create payments
agnara app create recommendations
```

The project can contain many apps, but each app is a **business module**, not a protocol-specific application.

```text
commerce
├── users
├── catalog
├── payments
└── recommendations
```

Each generated app uses modular hexagonal boundaries by default:

```text
payments/
├── domain/
├── application/
├── adapters/
│   ├── inbound/
│   └── outbound/
└── tests/
```

The implemented generator supports the default modular-hexagonal layout,
`--dry-run` and `--json`. Exposure selection (`--with`), profiles and a
`minimal` template are not implemented. Add each generated capability registry
to `bootstrap.py` using the printed instructions.

Convenience commands such as:

```bash
agnara app-mcp tools
agnara app-api catalog
```

are design proposals and are not implemented in this alpha.

Read:

- `docs/APPLICATION_MODEL.md`
- `docs/CLI_SPEC.md`
- `docs/SCAFFOLDING.md`
- `docs/PROJECT_MANIFEST.md`

## Agentic development lifecycle

Agnara is not only agent-compatible at runtime; the repository itself is designed for autonomous software engineering.

Development follows:

```text
Backlog
→ GitHub Issue
→ short-lived branch
→ implementation
→ tests / quality gates
→ commit
→ attribution verification
→ Pull Request
→ review
→ merge
→ next Issue
```

Read:

- `GIT_WORKFLOW.md`
- `AGENT_OPERATING_MODEL.md`
- `AGENTS.md`

Agents are expected to leave a normal, auditable GitHub trail that remains understandable to human maintainers.

Agent roles and Git authorship are separate: unverifiable agents are named in
Issues/PRs, while commit trailers are reserved for authorized,
GitHub-verifiable identities. See
`docs/adr/0019-ai-agent-attribution.md` and `GIT_WORKFLOW.md`.
