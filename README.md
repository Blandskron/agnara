# Agnara

Agnara is a Python capability runtime. Applications define a capability once
and expose it through transport adapters without making HTTP, MCP or another
protocol the semantic source of truth.

## Current direction

`0.1.0a8` is the verified publication baseline. Development now targets the
first product release, `1.0.0`; no further pre-release publication is planned.
See [the roadmap](ROADMAP.md) and the
[release plan](docs/releases/RELEASE_PLAN.md).

## Design

- Capabilities are application behaviour; routes and tools are exposures.
- The kernel is transport-neutral and uses only the Python standard library.
- Reflection and dependency graphs compile before invocation.
- Policies, schemas, errors and telemetry use protocol-neutral contracts.

Read [VISION.md](VISION.md), [PRINCIPLES.md](PRINCIPLES.md) and
[ARCHITECTURE.md](ARCHITECTURE.md) for the governing model. The supported
public surface is listed in [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

## Quick start

```python
import asyncio

from agnara import Agnara, Risk, StandardEffect
from agnara.core.di import DIContainer, DIRegistry, provider
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation, invoke_result
from agnara.policy import Principal


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
