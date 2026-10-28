"""Direct idempotency with explicit application-owned authority and storage.

Run with `uv run python examples/direct_idempotency.py` from the checkout.
The companion guide is docs/DIRECT_IDEMPOTENCY.md.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

from agnara import Agnara, CapabilityId, Principal
from agnara.di import DIContainer, DIRegistry
from agnara.execution import (
    CanonicalResult,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    IdempotencyInvocation,
    IdempotencyScope,
    InMemoryIdempotencyStore,
    Invocation,
    Success,
)

CAPTURE = CapabilityId.parse("orders.capture")


class ReceiptCodec:
    """This application stores only its own bounded successful receipt text."""

    def encode(self, value: object, /) -> bytes:
        if not isinstance(value, str):
            raise TypeError("capture must produce a receipt string")
        return value.encode("utf-8")

    def decode(self, payload: bytes, /) -> object:
        return payload.decode("utf-8")


def fingerprint(order_id: str, amount_cents: int) -> bytes:
    """Hash a canonical representation of every caller-controlled input."""
    canonical = json.dumps(
        {"amount_cents": amount_cents, "order_id": order_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).digest()


async def demonstrate() -> tuple[dict[str, CanonicalResult], list[tuple[str, int]]]:
    app = Agnara("orders")
    effects: list[tuple[str, int]] = []

    @app.capability(scopes=("orders:write",), idempotent=True, output=str)
    def capture(order_id: str, amount_cents: int) -> str:
        # A local stand-in for one business effect; no payment is made.
        effects.append((order_id, amount_cents))
        return f"receipt-{len(effects)}"

    capabilities = app.compile()
    dependencies = DIRegistry()
    plan = ExecutionPlan.compile(capabilities[CAPTURE], dependencies)
    container = DIContainer(dependencies)
    runtime = CapabilityRuntime(capabilities, [plan], container)
    store = InMemoryIdempotencyStore()  # One process; records vanish on restart.
    codec = ReceiptCodec()

    async def call(
        principal: Principal, *, amount_cents: int = 2500, key: str = "capture-A-1"
    ) -> CanonicalResult:
        # A real host authenticates before constructing Principal and decides
        # which stable selector is approved for this operation. Neither comes
        # from Invocation.metadata or a request/correlation identifier.
        order_id = "A-1"
        selector = IdempotencyInvocation(
            IdempotencyScope(
                CAPTURE,
                principal.identity,
                key,
                fingerprint(order_id, amount_cents),
            ),
            store,
            codec,
            lease_ttl=30,
            result_ttl=60,
        )
        context = ExecutionContext(
            Invocation(CAPTURE, {"order_id": order_id, "amount_cents": amount_cents}, {}),
            container,
            principal=principal,
            idempotency=selector,
        )
        return await runtime.invoke_result(context)

    try:
        alice = Principal("customer-alice", scopes={"orders:write"})
        alice_without_scope = Principal("customer-alice", scopes=set())
        bob = Principal("customer-bob", scopes={"orders:write"})
        outcomes = {
            "first": await call(alice),
            "duplicate": await call(alice),
            "changed_input": await call(alice, amount_cents=3000),
            "permission_lost": await call(alice_without_scope),
            "other_principal": await call(bob),
        }
        return outcomes, effects
    finally:
        await runtime.aclose()


async def main() -> None:
    outcomes, effects = await demonstrate()
    for label, outcome in outcomes.items():
        match outcome:
            case Success(value=value):
                print(f"{label}: {value}")
            case Failure(code=code):
                print(f"{label}: {code.value}")
    print(f"effects: {effects}")


if __name__ == "__main__":
    asyncio.run(main())
