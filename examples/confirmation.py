"""Verifier-backed confirmation with a local demonstration approval authority.

Run with ``uv run python examples/confirmation.py``. See docs/CONFIRMATION.md.
No real approval is collected and no catalog data is changed.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from agnara import (
    Agnara,
    CapabilityId,
    ConfirmationEvidence,
    ConfirmationVerdict,
    Principal,
)
from agnara.di import DIContainer, DIRegistry, provider
from agnara.execution import (
    CanonicalResult,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    Success,
    invoke_result,
)


def input_binding(payload: dict[str, Any]) -> tuple[str, str] | None:
    """The authority's exact input contract, checked before kernel validation."""
    if len(payload) != 2:
        return None
    sku, reason = payload.get("sku"), payload.get("reason")
    if type(sku) is not str or type(reason) is not str:
        return None
    return sku, reason


@dataclass
class DemoClock:
    """An injected clock makes expiry demonstrations deterministic."""

    now: float = 100.0


@dataclass(frozen=True, slots=True)
class Approval:
    capability_id: CapabilityId
    actor: str
    inputs: tuple[str, str]
    expires_at: float


class DemoAuthority:
    """One-process, one-event-loop fixture; not a durable approval service.

    A host would authenticate approvers and collect their decision separately.
    Only the trusted composition root calls approve here. The lock serializes
    verification/consumption among tasks on this loop; it is not a thread lock.
    """

    def __init__(self, clock: DemoClock) -> None:
        self.clock = clock
        self.calls = 0
        self._records: dict[str, Approval] = {}
        self._lock = asyncio.Lock()

    def approve(self, invocation: Invocation, principal: Principal) -> ConfirmationEvidence:
        inputs = input_binding(invocation.payload)
        if inputs is None:
            raise ValueError("approval requires the exact application input shape")
        reference = secrets.token_urlsafe(24)
        self._records[reference] = Approval(
            invocation.capability_id, principal.identity, inputs, self.clock.now + 30
        )
        return ConfirmationEvidence(reference)

    async def verify(
        self,
        evidence: ConfirmationEvidence,
        *,
        capability_id: CapabilityId,
        invocation: Invocation,
        principal: Principal,
    ) -> ConfirmationVerdict:
        async with self._lock:
            self.calls += 1
            if type(evidence.value) is not str:
                return ConfirmationVerdict.INVALID
            approval = self._records.get(evidence.value)
            if approval is None:
                return ConfirmationVerdict.INVALID
            if self.clock.now >= approval.expires_at:
                del self._records[evidence.value]
                return ConfirmationVerdict.INVALID
            if (
                approval.capability_id != capability_id
                or invocation.capability_id != capability_id
                or approval.actor != principal.identity
                or approval.inputs != input_binding(invocation.payload)
            ):
                return ConfirmationVerdict.INVALID
            # Single-use is atomic with validation on this event loop. Approval
            # is consumed before dependencies/handler work, not after an effect.
            del self._records[evidence.value]
            return ConfirmationVerdict.VALID


class Catalog:
    """A stand-in for an invocation-owned application dependency."""


async def demonstrate() -> tuple[dict[str, CanonicalResult], list[str]]:
    clock = DemoClock()
    authority = DemoAuthority(clock)
    effects: list[str] = []
    app = Agnara("catalog")

    @provider()
    async def provide_catalog() -> AsyncIterator[Catalog]:
        effects.append("resource.open")
        try:
            yield Catalog()
        finally:
            effects.append("resource.close")

    @app.capability(scopes=("catalog:write",), confirmation="required", output=str)
    def archive(sku: str, reason: str, catalog: Catalog) -> str:
        effects.append(f"archive:{sku}")
        return f"Archived {sku}: {reason}"

    dependencies = DIRegistry()
    dependencies.bind(Catalog, provide_catalog)
    plan = ExecutionPlan.compile(
        app.compile()["catalog.archive"], dependencies, confirmation_verifier=authority
    )
    container = DIContainer(dependencies)
    alice = Principal("alice", scopes={"catalog:write"})
    invocation = Invocation(plan.definition.id, {"sku": "A-1", "reason": "retired"}, {})

    async def call(
        evidence: ConfirmationEvidence | None = None,
        *,
        actor: Principal = alice,
        target: Invocation = invocation,
    ) -> CanonicalResult:
        return await invoke_result(
            plan,
            ExecutionContext(target, container, principal=actor, confirmation_evidence=evidence),
        )

    try:
        results = {"missing": await call()}
        results["metadata_flag"] = await call(
            target=Invocation(plan.definition.id, invocation.payload, {"confirmed": True})
        )
        results["forged"] = await call(ConfirmationEvidence("unknown-approval"))
        approved = authority.approve(invocation, alice)
        results["changed_input"] = await call(
            approved,
            target=Invocation(plan.definition.id, {"sku": "A-2", "reason": "retired"}, {}),
        )
        results["other_actor"] = await call(
            approved, actor=Principal("bob", scopes={"catalog:write"})
        )
        results["scope_lost"] = await call(approved, actor=Principal("alice"))
        results["approved"] = await call(approved)
        results["replay"] = await call(approved)
        expired = authority.approve(invocation, alice)
        clock.now += 30  # Inclusive expiry, with no sleep.
        results["expired"] = await call(expired)
        return results, effects
    finally:
        await container.aclose()


def main() -> None:
    results, effects = asyncio.run(demonstrate())
    for name, result in results.items():
        if isinstance(result, Success):
            print(f"{name}: {result.value}")
        elif isinstance(result, Failure):
            print(f"{name}: {result.code.value}")
    print(f"effects: {effects}")


if __name__ == "__main__":
    main()
