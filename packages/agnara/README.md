# agnara

> **Capability-native Python for the agentic era.**

Agnara is a Python 3.14-native capability framework for services meant to be
consumed by humans, applications and AI agents without making HTTP the centre
of the architecture. A capability is declared once, with its effects, risk and
confirmation requirements, and later exposed through whichever protocol the
caller needs.

This distribution is `agnara`, the capability-first, transport-neutral
execution kernel: the capability model, registry, execution context,
dependency graph, policies, execution planning and canonical errors. It
depends on nothing but the standard library.

## Status: alpha

`0.1.0a1` is the first public release — an architectural proof that Agnara
installs and runs as a real Python distribution. It is **not
production-ready**, the public API may change without a deprecation cycle, and
it makes no claim of protocol conformance, benchmark leadership or security
guarantees.

## Install

```bash
pip install agnara==0.1.0a1
```

Requires CPython 3.14 or newer.

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
        ),
    )
    print(outcome)


asyncio.run(main())
```

The declared function is returned unchanged, so it stays directly callable and
directly testable. Registration is a side effect on the application, not a
transformation of the function.

## What this release includes

- capability declaration and a deterministic, freezable registry;
- stable capability identity, plus effect, risk, idempotency and confirmation
  metadata;
- a schema port with a standard-library adapter and compiled per-parameter
  input validation;
- dependency injection with compile-time graph validation and scoped
  resolution;
- execution plans, direct invocation and optional monotonic deadlines;
- protocol-neutral policies, principals and scope evaluation;
- canonical `Success` / `Failure` outcomes with stable failure codes;
- structured execution telemetry hooks.

## What it does not include

The HTTP/ASGI, OpenAPI, MCP and CLI adapters exist in the Agnara repository but
were **not** published to PyPI in `0.1.0a1`, so they cannot be installed with
`pip` yet. Events, A2A and the telemetry bridge are likewise repository-only.

## Frozen value semantics

Core value types such as `CapabilityId` and `CapabilityDefinition` are
immutable and slotted. Assigning or deleting either a declared field or an
unknown attribute raises `dataclasses.FrozenInstanceError`; a typo never
attaches new state and does not leak CPython's internal slots error.

## Confirmation boundary

Capabilities declared with `confirmation="required"` need an
application-provided `ConfirmationVerifier` when their `ExecutionPlan` is
compiled. Each invocation may carry an explicit opaque `ConfirmationEvidence`
on `ExecutionContext`; values in generic invocation metadata are not approval.

The verifier receives the exact capability id, invocation, and principal and
owns authenticity, input canonicalization, expiry, and replay protection.
Missing evidence terminates execution with an interaction request. Rejected
evidence terminates it as forbidden. Both outcomes occur before dependency
construction or handler effects, and `invoke_result()` maps them to stable
protocol-neutral failure codes.

## Links

- Source, architecture and decision records:
  <https://github.com/Blandskron/agnara>
- Changelog:
  <https://github.com/Blandskron/agnara/blob/main/CHANGELOG.md>
- Architecture:
  <https://github.com/Blandskron/agnara/blob/main/ARCHITECTURE.md>
- Longer example:
  <https://github.com/Blandskron/agnara/blob/main/examples/quickstart.py>

## License

Apache License 2.0.
