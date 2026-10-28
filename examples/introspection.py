"""Filtered protocol-neutral discovery through the governed public API.

Run with ``uv run python examples/introspection.py``. See docs/INTROSPECTION.md.
Principals are local fixtures; no authentication or discovery server is built.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from agnara import Agnara, AnonymousPrincipal, Principal
from agnara.di import DIContainer, DIRegistry, provider
from agnara.execution import ExecutionContext, ExecutionPlan, Failure, Invocation, invoke_result
from agnara.exposure import compile_exposures
from agnara.introspection import (
    AllCapabilitiesVisible,
    DiscoveryVisibility,
    Hiding,
    NoCapabilityVisible,
    ScopeVisible,
    describe_app,
    filter_snapshot,
    snapshot,
)
from agnara_http import Http
from agnara_mcp import Mcp


class Ledger:
    """Application dependency whose value never belongs in discovery."""

    secret = "demo-runtime-secret"


async def demonstrate() -> dict[str, Any]:
    effects: list[str] = []
    app = Agnara("catalog")
    dependencies = DIRegistry()

    @provider()
    async def provide_ledger() -> AsyncIterator[Ledger]:
        effects.append("resource.open")
        try:
            yield Ledger()
        finally:
            effects.append("resource.close")

    dependencies.bind(Ledger, provide_ledger)

    @app.capability(description="Report catalog health.", output=str)
    def health() -> str:
        return "ok"

    @app.capability(description="Read one catalog item.", scopes={"catalog:read"}, output=str)
    def lookup(sku: str, ledger: Ledger) -> str:
        effects.append(f"lookup:{sku}")
        return f"Item {sku}"

    @app.capability(description="Refresh the local demo cache.", output=str)
    def refresh(ledger: Ledger) -> str:
        effects.append("refresh")
        return "refreshed"

    http = Http("public")
    http.get("/health", health)
    mcp = Mcp(app, surface="agents")
    mcp.tool(lookup)
    mcp.tool(refresh)
    capabilities = app.compile()
    plans = [ExecutionPlan.compile(item, dependencies) for item in capabilities.values()]
    asgi = http.compile(capabilities, dependencies=dependencies)
    exposures = compile_exposures(capabilities, [asgi.exposures, mcp.compile_surface()])
    source = snapshot([describe_app(app, plans, dependencies=dependencies, exposures=exposures)])
    visibility = DiscoveryVisibility.agent_safe(Hiding({"catalog.refresh"}, ScopeVisible()))
    anonymous = AnonymousPrincipal()
    reader = Principal("demo-reader", scopes={"catalog:read"})
    views = {
        "anonymous": filter_snapshot(source, visibility, anonymous),
        "reader": filter_snapshot(source, visibility, reader),
        "identity_only": filter_snapshot(
            source, DiscoveryVisibility.identity_only(visibility.rule), reader
        ),
        "disabled": filter_snapshot(
            source, DiscoveryVisibility.identity_only(NoCapabilityVisible()), reader
        ),
        # This explicit publication decision demonstrates that listing a scoped
        # capability does not confer permission to execute it.
        "listed_without_authority": filter_snapshot(
            source, DiscoveryVisibility.agent_safe(AllCapabilitiesVisible()), anonymous
        ),
    }
    documents = {name: view.json_data() for name, view in views.items()}
    discovery_effects = effects.copy()
    container = DIContainer(dependencies)

    async def call(name: str, principal: Principal, payload: dict[str, Any]):
        plan = next(item for item in plans if item.definition.id.name == name)
        return await invoke_result(
            plan,
            ExecutionContext(
                Invocation(plan.definition.id, payload, {}), container, principal=principal
            ),
        )

    try:
        denied = await call("lookup", anonymous, {"sku": "A-1"})
        denied_effects = effects.copy()
        hidden = await call("refresh", anonymous, {})
        allowed = await call("lookup", reader, {"sku": "A-1"})
        return {
            "source": source,
            "views": views,
            "documents": documents,
            "discovery_effects": discovery_effects,
            "denied_effects": denied_effects,
            "results": {"denied": denied, "hidden": hidden, "allowed": allowed},
            "effects": effects,
        }
    finally:
        await container.aclose()


async def bounded_demonstration() -> dict[str, Any]:
    async with asyncio.timeout(5):
        return await demonstrate()


def main() -> None:
    outcome = asyncio.run(bounded_demonstration())
    for name, document in outcome["documents"].items():
        ids = [item["id"] for app in document["applications"] for item in app["capabilities"]]
        print(f"{name}: {ids}; transports={document['transports']}")
    for name, result in outcome["results"].items():
        print(f"{name}: {result.code.value if isinstance(result, Failure) else result.value}")
    print(f"discovery_effects: {outcome['discovery_effects']}")
    print(f"denied_effects: {outcome['denied_effects']}")
    print(f"effects: {outcome['effects']}")


if __name__ == "__main__":
    main()
