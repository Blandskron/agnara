"""Run the provisional A2A profile with the official client, without sockets.

Run ``uv run python examples/a2a_service.py`` from this unreleased checkout.
The published 1.0.3 A2A wheel cannot run this example. See docs/A2A_SERVICE.md.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any

import httpx
from a2a.client.transports.jsonrpc import JsonRpcTransport
from a2a.types import a2a_pb2
from google.protobuf import json_format

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import ExecutionPlan
from agnara_a2a import A2A_PROTOCOL_VERSION, A2a, A2aAgentCard, build_a2a_app

URL = "http://agent.test/"
HEADERS = {"Authorization": "Bearer demo-reader", "A2A-Version": A2A_PROTOCOL_VERSION}
CHALLENGE = 'Bearer realm="agent.test"'


class Pool:
    """Container-owned local fixture; no database or external service."""


class Ledger:
    """Invocation-owned local fixture, never a caller argument."""


def resolve_principal(scope: Mapping[str, Any]) -> Principal | None:
    """Read only the identity verified by the host, never caller JSON."""
    return scope.get("demo.verified_principal")


@asynccontextmanager
async def lifespan(application: Any, events: list[str]) -> AsyncIterator[None]:
    """Drive and join ASGI lifespan on the same loop as the client/container."""
    incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    try:
        async with asyncio.timeout(5), asyncio.TaskGroup() as owned:
            owned.create_task(application({"type": "lifespan"}, incoming.get, outgoing.put))
            await incoming.put({"type": "lifespan.startup"})
            if (await outgoing.get())["type"] != "lifespan.startup.complete":
                raise RuntimeError("A2A example startup failed")
            try:
                yield
            finally:
                await incoming.put({"type": "lifespan.shutdown"})
                if (await outgoing.get())["type"] != "lifespan.shutdown.complete":
                    raise RuntimeError("A2A example shutdown failed")
    finally:
        events.append("lifespan.close")


@asynccontextmanager
async def connect(
    events: list[str], *, wrap: Callable[[Any], Any] | None = None
) -> AsyncIterator[tuple[httpx.AsyncClient, JsonRpcTransport]]:
    """Compose and own the service; optionally install an application-owned wrapper."""
    app = Agnara("catalog")

    @provider(scope=Scope.SINGLETON)
    async def provide_pool() -> AsyncIterator[Pool]:
        events.append("pool.open")
        try:
            yield Pool()
        finally:
            events.append("pool.close")

    @provider()
    async def provide_ledger(pool: Pool) -> AsyncIterator[Ledger]:
        events.append("ledger.open")
        try:
            yield Ledger()
        finally:
            events.append("ledger.close")

    @app.capability(scopes=("catalog:read",), output=int)
    def total(quantity: int, ledger: Ledger) -> int:
        events.append(f"total:{quantity}")
        if quantity < 0:
            raise RuntimeError("demo-private-diagnostic")
        return quantity * 10

    dependencies = DIRegistry()
    dependencies.bind(Pool, provide_pool)
    dependencies.bind(Ledger, provide_ledger)
    a2a = A2a(app, surface="agents")
    a2a.skill(total, id="total", name="Total", description="Prices a quantity", tags=("catalog",))
    plans = [ExecutionPlan.compile(d, dependencies) for d in app.compile().values()]
    container = DIContainer(dependencies)
    try:
        application = build_a2a_app(
            a2a.compile(),
            plans,
            container,
            card=A2aAgentCard(name="Catalog", description="Example pricing", version="demo"),
            url=URL,
            principals=resolve_principal,
            challenge=CHALLENGE,
            timeout=2,
        )
        if wrap is not None:
            application = wrap(application)

        async def host(scope: Any, receive: Any, send: Any) -> None:
            # Toy authentication at the host boundary, not production token
            # verification. Only this fixed table grants demo identities.
            tokens = {
                b"Bearer demo-reader": Principal("reader", scopes={"catalog:read"}),
                b"Bearer demo-unscoped": Principal("unscoped"),
            }
            credential = dict(scope.get("headers", ())).get(b"authorization")
            principal = tokens.get(credential)
            await application({**scope, "demo.verified_principal": principal}, receive, send)

        async with lifespan(host, events):
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=host), base_url=URL, headers=HEADERS
                ) as http:
                    card_response = await http.get("/.well-known/agent-card.json")
                    card_response.raise_for_status()
                    card = json_format.ParseDict(card_response.json(), a2a_pb2.AgentCard())
                    try:
                        async with JsonRpcTransport(
                            http, card, URL, is_shared_httpx=True
                        ) as client:
                            yield http, client
                    finally:
                        events.append("client.close")
            finally:
                events.append("http.close")
    finally:
        await container.aclose()
        events.append("container.close")


async def send(client: JsonRpcTransport, quantity: int) -> dict[str, Any]:
    """Use the official SDK for the successful message exchange."""
    request = json_format.ParseDict(
        {
            "message": {
                "messageId": "demo-input",
                "role": "ROLE_USER",
                "parts": [{"data": {"quantity": quantity}}],
            }
        },
        a2a_pb2.SendMessageRequest(),
    )
    return json_format.MessageToDict(await client.send_message(request))


async def rpc(http: httpx.AsyncClient, data: dict[str, Any], **options: Any) -> dict[str, Any]:
    """Inspect raw JSON-RPC errors as well as the official client's success."""
    response = await http.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": "demo",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "demo-input",
                    "role": "ROLE_USER",
                    "parts": [{"data": data}],
                }
            },
        },
        **options,
    )
    response.raise_for_status()
    return response.json()


async def demonstrate(*, wrap: Callable[[Any], Any] | None = None) -> dict[str, Any]:
    events: list[str] = []
    async with asyncio.timeout(10), connect(events, wrap=wrap) as (http, client):
        missing = await http.post("/", content=b"{", headers={"Authorization": "unknown"})
        results = {
            "invalid_input": await rpc(http, {"quantity": "bad"}),
            "forged_dependency": await rpc(http, {"quantity": 3, "ledger": "forged"}),
            "denied": await rpc(
                http, {"quantity": 3}, headers={"Authorization": "Bearer demo-unscoped"}
            ),
        }
        rejected_effects = list(events)
        results["valid"] = await send(client, 3)
        results["handler_failure"] = await rpc(http, {"quantity": -1})
        results["recovered"] = await send(client, 1)
    return {
        "protocol": A2A_PROTOCOL_VERSION,
        "unauthenticated": (missing.status_code, missing.headers.get("www-authenticate")),
        "results": results,
        "rejected_effects": rejected_effects,
        "events": events,
    }


def main() -> None:
    outcome = asyncio.run(demonstrate())
    print(f"protocol: {outcome['protocol']}")
    print(f"unauthenticated: {outcome['unauthenticated'][0]}")
    for name, result in outcome["results"].items():
        if "error" in result:
            value = result["error"]["data"][0]["metadata"]["agnaraCode"]
        else:
            value = result["message"]["parts"][0]["data"]["result"]
        print(f"{name}: {value}")
    print(f"events: {outcome['events']}")


if __name__ == "__main__":
    main()
