# Agnara

Agnara is a Python capability runtime. Applications define a capability once
and expose it through transport adapters without making HTTP, MCP or another
protocol the semantic source of truth.

## Why Agnara

Agnara lets one application capability serve direct Python callers and explicit
transport exposures without putting protocol objects in the business model.
The execution kernel uses only the Python standard library and requires Python
3.14 or newer. The seven official distributions share one version; this tree
prepares the 1.0.3 documentation and packaging baseline.

```bash
pip install "agnara==1.0.3"
```

Install `agnara-http`, `agnara-mcp`, `agnara-cli` or `agnara-telemetry` at the
same version when an application uses those surfaces. `agnara-a2a` and
`agnara-events` reserve package names and expose no runtime API.

## Capability-first model

- Capabilities are application behaviour; routes and tools are exposures.
- The kernel is transport-neutral and uses only the Python standard library.
- Reflection and dependency graphs compile before invocation.
- Policies, schemas, errors and telemetry use protocol-neutral contracts.

Read [VISION.md](VISION.md), [PRINCIPLES.md](PRINCIPLES.md) and
[ARCHITECTURE.md](ARCHITECTURE.md) for the governing model. The supported
imports and compatibility rules are in [PUBLIC_API.md](docs/PUBLIC_API.md) and
the generated [API reference](docs/API_REFERENCE.md).

## Quick start

```python
import asyncio

from agnara import Agnara, Risk, StandardEffect
from agnara.di import DIContainer, DIRegistry, provider
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation, invoke_result
from agnara import Principal


class Ledger:
    def refund(self, payment_id: str, amount_cents: int) -> str:
        return f"refunded {amount_cents} cents for {payment_id}"


@provider()
def provide_ledger() -> Ledger:
    return Ledger()


app = Agnara("billing")


@app.capability(
    description="Refund a captured payment.",
    scopes=("billing:write",),
    effects=(StandardEffect.FINANCIAL_WRITE,),
    risk=Risk.HIGH,
)
def refund(payment_id: str, amount_cents: int, ledger: Ledger) -> str:
    return ledger.refund(payment_id, amount_cents)


async def main() -> None:
    capabilities = app.compile()
    dependencies = DIRegistry()
    dependencies.bind(Ledger, provide_ledger)
    plan = ExecutionPlan.compile(capabilities["billing.refund"], dependencies)
    outcome = await invoke_result(
        plan,
        ExecutionContext(
            Invocation(plan.definition.id, {"payment_id": "pay_123", "amount_cents": 2500}, {}),
            DIContainer(dependencies),
            principal=Principal("quickstart", scopes={"billing:write"}),
        ),
    )
    print(outcome)


asyncio.run(main())
```

The plan evaluates declared scopes before invoking the handler. The principal
comes from the application or host that authenticated the caller. Risk and
effect metadata describe the capability; they do not grant authorization.

## Surfaces and limits

| Distribution | Current role |
| --- | --- |
| `agnara` | Capability registry, compiled plans, DI, policy, canonical outcomes, streaming, direct idempotency and introspection. |
| `agnara-http` | ASGI HTTP, OpenAPI, documentation UIs, filtered discovery, Explorer and SSE. |
| `agnara-mcp` | Version-pinned MCP tool projection, authorization and invocation for the documented subset. |
| `agnara-cli` | Project/app scaffolding, inspection, graph, context and OpenAPI export commands. |
| `agnara-telemetry` | Explicit OpenTelemetry metrics and tracing hooks; the application owns its SDK and exporter. |
| `agnara-a2a`, `agnara-events` | Reserved namespaces with no public runtime API. |

Compiled snapshots and policies remain transport neutral. Streaming is pull
based in the kernel and has an HTTP SSE projection; it is not projected by the
MCP or reserved packages. Idempotency is explicit for direct complete-result
calls and is not an HTTP or MCP request-key feature. Confirmation requires an
application verifier. Introspection applies visibility rules before exporting
data; hiding an operation in a browser UI is not authorization.

Agnara can run standalone, inside a host framework, or beside host routes.
The host keeps ownership of authentication, routing, persistence and lifecycle.
See [interoperability](docs/INTEROPERABILITY.md), [security](SECURITY.md) and
the [threat model](docs/THREAT_MODEL.md) for evidence and limits.

## Operations and documentation

The [CLI and scaffolding guide](docs/CLI_SPEC.md) covers generated projects.
The [container guide](docs/CONTAINERS.md) covers the reference runtime and
digest pinning. [Documentation map](docs/DOCUMENTATION_MAP.md) identifies the
owner of each current contract. Public API stability is governed by
`docs/public-api.json`; the [quality gates](QUALITY_GATES.md) and
[contribution guide](CONTRIBUTING.md) describe verification and review.

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

Publication is a reviewed dispatch from `main`. The workflow verifies the
complete distribution set before it creates a tag; see
[docs/MAINTAINERS_RELEASE.md](docs/MAINTAINERS_RELEASE.md).

The reference container is published to GHCR and Docker Hub separately from
the Python distributions. PyPI is the Python package index; immutable release
tags and the mutable `:edge` image have different purposes. See the container
guide before pinning a deployment.

## License

Apache-2.0. See [LICENSE](LICENSE).
