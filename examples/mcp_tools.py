"""Discover and invoke Agnara tools through the pinned official MCP client.

Run with ``uv run python examples/mcp_tools.py``. See docs/MCP_TOOLS.md.
This is an anonymous in-process connection, not a network or OAuth example.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from mcp_types import CallToolResult, TextContent

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, provider
from agnara.execution import ExecutionPlan
from agnara_mcp import (
    Mcp,
    McpAuthenticatedIdentity,
    McpAuthorization,
    build_mcp_server,
)
from mcp import Client, MCPError


class Ledger:
    """An invocation-owned stand-in; no external database is contacted."""


def reject_authenticated(identity: McpAuthenticatedIdentity) -> Principal:
    """The anonymous tutorial deliberately configures no authenticated mapper.

    A real host must install its own trusted mapping of verifier-approved
    identity facts. Neither a bearer string nor tool arguments grant authority.
    """
    raise ValueError("authenticated identity mapping is not configured in this example")


def text_document(result: CallToolResult) -> dict[str, Any]:
    """Decode the adapter's one JSON text block, not arbitrary MCP content."""
    if len(result.content) != 1 or not isinstance(result.content[0], TextContent):
        raise ValueError("this example expects one JSON text block")
    return json.loads(result.content[0].text)


async def demonstrate() -> dict[str, Any]:
    app = Agnara("catalog")
    effects: list[str] = []

    @provider()
    async def provide_ledger() -> AsyncIterator[Ledger]:
        effects.append("resource.open")
        try:
            yield Ledger()
        finally:
            effects.append("resource.close")

    @app.capability(output=int)
    def total(quantity: int, ledger: Ledger, unit_price: int = 10) -> int:
        effects.append(f"total:{quantity}:{unit_price}")
        return quantity * unit_price

    @app.capability(scopes=("catalog:read",), output=str)
    def private(ledger: Ledger) -> str:
        effects.append("private.handler")
        return "private catalog"

    @app.capability(output=str)
    def broken(ledger: Ledger) -> str:
        effects.append("broken.handler")
        raise RuntimeError("demo-private-diagnostic")

    dependencies = DIRegistry()
    dependencies.bind(Ledger, provide_ledger)
    mcp = Mcp(app, surface="agents")
    mcp.tool(total)
    mcp.tool(private)
    mcp.tool(broken)
    capabilities = app.compile()
    exposures = mcp.compile()
    plans = [
        ExecutionPlan.compile(definition, dependencies) for definition in capabilities.values()
    ]
    container = DIContainer(dependencies)
    try:
        server = build_mcp_server(
            exposures,
            plans,
            container,
            name="catalog-example",
            version="demo",
            authorization=McpAuthorization(exposures, reject_authenticated),
            timeout=2,
        )
        # The client owns its connection tasks. The application owns the DI
        # container and closes it after the client leaves, including on failure.
        async with asyncio.timeout(10), Client(server, mode="auto") as client:
            listing = await client.list_tools()
            results = {
                "invalid_input": await client.call_tool("catalog.total", {"quantity": "bad"}),
                "forged_dependency": await client.call_tool(
                    "catalog.total", {"quantity": 3, "ledger": "caller-supplied"}
                ),
                "denied": await client.call_tool("catalog.private", {}),
            }
            try:
                await client.call_tool("catalog.missing", {})
            except MCPError as error:
                unknown_code = error.code
            else:
                raise RuntimeError("unknown tool unexpectedly accepted")
            rejected_effects = list(effects)
            results["valid"] = await client.call_tool("catalog.total", {"quantity": 3})
            results["handler_failure"] = await client.call_tool("catalog.broken", {})
            results["recovered"] = await client.call_tool("catalog.total", {"quantity": 1})
            return {
                "protocol": client.protocol_version,
                "listing": listing,
                "results": results,
                "unknown_code": unknown_code,
                "rejected_effects": rejected_effects,
                "effects": effects,
            }
    finally:
        await container.aclose()


def main() -> None:
    outcome = asyncio.run(demonstrate())
    print(f"protocol: {outcome['protocol']}")
    print(f"tools: {[tool.name for tool in outcome['listing'].tools]}")
    for name in ("valid", "invalid_input", "forged_dependency", "denied", "handler_failure"):
        result = outcome["results"][name]
        document = text_document(result)
        print(f"{name}: {document['code'] if result.is_error else document['result']}")
    print(f"unknown_tool: protocol_error ({outcome['unknown_code']})")
    print(f"recovered: {text_document(outcome['results']['recovered'])['result']}")
    print(f"effects: {outcome['effects']}")


if __name__ == "__main__":
    main()
