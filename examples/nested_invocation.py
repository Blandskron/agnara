"""Run with `uv run python examples/nested_invocation.py` from the checkout.

Same-application composition through public API; see docs/NESTED_INVOCATION.md.
"""

from __future__ import annotations

import asyncio

from agnara import Agnara, CapabilityId, Principal
from agnara.di import DIContainer, DIRegistry
from agnara.execution import (
    CanonicalResult,
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    Success,
)


async def demonstrate(principal: Principal) -> tuple[CanonicalResult, list[str]]:
    """Build an isolated application and report which handlers actually ran."""
    app = Agnara("catalog")
    calls: list[str] = []  # Owned by this sequential demonstration only.

    @app.capability(scopes=("catalog:read",), output=str)
    def product(sku: str) -> str:
        calls.append("product")
        return f"{sku}: widget"

    @app.capability(scopes=("summary:read",), output=str)
    async def summary(sku: str, invoker: CapabilityInvoker) -> str:
        calls.append("summary")
        child = await invoker.invoke(CapabilityId.parse("catalog.product"), {"sku": sku})
        match child:
            case Success(value=value):
                return f"Summary: {value}"
            case Failure(code=code):
                # Explicit application fallback: the summary succeeds while
                # reporting that the child could not supply product details.
                return f"Product unavailable: {code.value}"

    capabilities = app.compile()
    dependencies = DIRegistry()
    plans = [ExecutionPlan.compile(capabilities[key], dependencies) for key in capabilities]
    container = DIContainer(dependencies)
    runtime = CapabilityRuntime(capabilities, plans, container)
    try:
        outcome = await runtime.invoke_result(
            ExecutionContext(
                Invocation(CapabilityId.parse("catalog.summary"), {"sku": "A-1"}, {}),
                container,
                principal=principal,
            )
        )
        return outcome, calls
    finally:
        # The application owns the container, including exceptional exits.
        await runtime.aclose()


async def main() -> None:
    # Fixture identities only. A real host authenticates its caller before
    # constructing Principal; request parameters cannot grant these scopes.
    for label, scopes in (
        ("authorized", {"summary:read", "catalog:read"}),
        ("child denied", {"summary:read"}),
        ("parent denied", {"catalog:read"}),
    ):
        outcome, calls = await demonstrate(Principal("reader", scopes=scopes))
        match outcome:
            case Success(value=value):
                print(f"{label}: {value}; handlers={calls}")
            case Failure(code=code):
                print(f"{label}: {code.value}; handlers={calls}")


if __name__ == "__main__":
    asyncio.run(main())
