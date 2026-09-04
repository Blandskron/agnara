"""Agnara 0.1.0a1 quick start.

Runs against the published `agnara` distribution using public API only:

    pip install agnara==0.1.0a1
    python quickstart.py

It demonstrates the whole `0.1.0a1` surface: capability declaration with
security metadata, startup compilation and freezing, dependency injection,
schema-validated direct invocation, and canonical results.

Transport adapters (HTTP, OpenAPI, MCP) live in sibling packages that are not
part of this release. See the release notes for the exact published scope.
"""

from __future__ import annotations

import asyncio

from agnara import Agnara, Confirmation, Risk, StandardEffect
from agnara.core.di import DIContainer, DIRegistry, provider
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    Success,
    invoke_result,
)


class Ledger:
    """A stand-in for whatever the application really talks to."""

    def refund(self, payment_id: str, amount_cents: int) -> str:
        return f"refunded {amount_cents} cents for {payment_id}"


@provider()
def provide_ledger() -> Ledger:
    return Ledger()


app = Agnara("billing")


@app.capability(
    description="Refund a captured payment.",
    scopes=("billing:write",),
    effects=(StandardEffect.FINANCIAL_WRITE, StandardEffect.EXTERNAL_WRITE),
    risk=Risk.HIGH,
    confirmation=Confirmation.NEVER,
    idempotent=False,
)
def refund(payment_id: str, amount_cents: int, ledger: Ledger) -> str:
    return ledger.refund(payment_id, amount_cents)


@app.capability(description="Read a payment's status.", idempotent=True)
def payment_status(payment_id: str) -> str:
    return f"{payment_id}: captured"


async def main() -> None:
    # 1. Startup compilation. The registry freezes; nothing registers later.
    capabilities = app.compile()
    print(f"app: {app.name} ({len(capabilities)} capabilities)")
    for capability_id in capabilities:  # declaration order, frozen at compile
        definition = capabilities[capability_id]
        print(
            f"  {capability_id}"
            f"  risk={definition.risk.value}"
            f"  effects={sorted(str(effect) for effect in definition.effects)}"
            f"  scopes={sorted(definition.scopes)}"
        )

    # 2. Bind dependencies and compile one execution plan per capability.
    dependencies = DIRegistry()
    dependencies.bind(Ledger, provide_ledger)
    plan = ExecutionPlan.compile(capabilities["billing.refund"], dependencies)

    # The compiled input schema excludes `ledger`: dependencies are
    # runtime-owned and a caller can never supply them.
    for name, schema in plan.input_schemas.items():
        print(f"  input {name}: {schema}")
    print(f"  protected (runtime-owned): {sorted(plan.protected_parameters)}")

    # 3. Invoke directly. No HTTP, no server, no transport.
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
    match outcome:
        case Success(value=value):
            print(f"\nsuccess: {value}")
        case Failure(code=code, message=message):
            print(f"\nfailure: {code} {message}")

    # 4. Bad input is a canonical failure, not an exception or a 422.
    rejected = await invoke_result(
        plan,
        ExecutionContext(
            Invocation(
                capability_id=plan.definition.id,
                payload={"payment_id": "pay_123", "amount_cents": "not-an-int"},
                metadata={},
            ),
            DIContainer(dependencies),
        ),
    )
    match rejected:
        case Failure(code=code, message=message):
            print(f"rejected: {code} {message}")
        case Success():  # pragma: no cover - the payload is invalid on purpose
            raise AssertionError("invalid input must not succeed")


if __name__ == "__main__":
    asyncio.run(main())
