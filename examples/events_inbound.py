"""Run the provisional inbound CloudEvents 1.0 and AsyncAPI 3.1.0 example.

Run ``uv run python examples/events_inbound.py`` from a synchronized checkout.
See docs/EVENTS_INBOUND.md.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import ExecutionPlan, Failure, FailureCode
from agnara.exposure import compile_exposures
from agnara_events import (
    CLOUDEVENTS_JSON_CONTENT_TYPE,
    AsyncAPIInfo,
    ConsumerBudgets,
    Delivery,
    compile_event_surface,
    compile_inbound_event,
    consume_inbound_events,
    declare_inbound_event,
    project_asyncapi,
)

EVENT_TYPE = "example.inventory.snapshot.v1"
EXACT_REVISION = 9007199254740993


class Ledger:
    """Invocation-owned local fixture; never supplied by event payloads."""


class MemoryDelivery:
    """In-memory manual-settlement delivery fixture."""

    def __init__(
        self,
        body: bytes,
        *,
        content_type: str | None = CLOUDEVENTS_JSON_CONTENT_TYPE,
        events: list[str] | None = None,
    ) -> None:
        self.body = body
        self.content_type = content_type
        self._events = events
        self.settlement: str | None = None

    async def acknowledge(self) -> None:
        self.settlement = "acknowledge"
        if self._events is not None:
            self._events.append("delivery.acknowledge")

    async def reject(self) -> None:
        self.settlement = "reject"
        if self._events is not None:
            self._events.append("delivery.reject")

    async def release(self) -> None:
        self.settlement = "release"
        if self._events is not None:
            self._events.append("delivery.release")


class MemorySource:
    """In-memory single-consumer delivery source."""

    def __init__(self, deliveries: list[MemoryDelivery]) -> None:
        self._queue: asyncio.Queue[Delivery | None] = asyncio.Queue()
        for item in deliveries:
            self._queue.put_nowait(item)
        self.stopped = False

    async def receive(self) -> Delivery | None:
        return await self._queue.get()

    async def stop_receiving(self) -> None:
        self.stopped = True


def _envelope(data: dict[str, object], *, event_type: str = EVENT_TYPE) -> bytes:
    return json.dumps(
        {
            "specversion": "1.0",
            "id": "evt-1",
            "source": "/inventory",
            "type": event_type,
            "datacontenttype": "application/json",
            "data": data,
        }
    ).encode()


async def demonstrate() -> dict[str, Any]:
    """Exercise outcomes, shutdown cleanup, and AsyncAPI export in one loop."""
    events: list[str] = []
    entered_block = asyncio.Event()
    app = Agnara("inventory")

    @provider(scope=Scope.INVOCATION)
    async def open_ledger() -> AsyncIterator[Ledger]:
        events.append("ledger.open")
        try:
            yield Ledger()
        finally:
            events.append("ledger.close")

    @app.capability(scopes=("inventory:write",), output=str)
    async def apply(sku: str, revision: int, mode: str, ledger: Ledger) -> str | Failure:
        events.append(f"apply:{sku}:{revision}:{mode}")
        if mode == "conflict":
            return Failure(FailureCode.CONFLICT, "stale snapshot revision")
        if mode == "transient":
            raise RuntimeError("private-broker-diagnostic-must-be-redacted")
        if mode == "block":
            entered_block.set()
            await asyncio.Event().wait()
        return "applied"

    compiled_app = app.compile()
    dependencies = DIRegistry()
    dependencies.bind(Ledger, open_ledger)
    definition = compiled_app["inventory.apply"]
    plan = ExecutionPlan.compile(definition, dependencies)
    container = DIContainer(dependencies)

    exposure = declare_inbound_event(
        definition,
        subscription_id="inventory-apply",
        event_type=EVENT_TYPE,
        principal=Principal("inventory-consumer", scopes={"inventory:write"}),
        public_address="inventory.snapshot.v1",
        summary="Apply inventory snapshot",
    )
    binding = compile_inbound_event(exposure, {definition.id: plan})
    exposures = compile_exposures(compiled_app, [compile_event_surface(binding)])
    asyncapi_doc = project_asyncapi(
        binding,
        AsyncAPIInfo(title="Inventory Events", version="1.0.0"),
    )

    deliveries = [
        MemoryDelivery(
            _envelope({"sku": "A-1", "revision": EXACT_REVISION, "mode": "ok"}),
            events=events,
        ),
        MemoryDelivery(
            _envelope({"sku": "A-1", "revision": EXACT_REVISION, "mode": "conflict"}),
            events=events,
        ),
        MemoryDelivery(
            _envelope({"sku": "A-1", "revision": 2.0, "mode": "ok"}),
            events=events,
        ),
        MemoryDelivery(
            _envelope({"sku": "A-1", "revision": 1, "mode": "ok"}, event_type="wrong.type"),
            events=events,
        ),
        MemoryDelivery(
            _envelope({"sku": "A-1", "revision": 2, "mode": "transient"}),
            events=events,
        ),
    ]
    source = MemorySource(deliveries)
    source._queue.put_nowait(None)

    try:
        diags = await consume_inbound_events(
            binding,
            container,
            source,
            budgets=ConsumerBudgets(attempt_seconds=2.0, shutdown_seconds=1.0),
            stop_event=asyncio.Event(),
        )

        # Demonstrate cooperative shutdown cancellation releasing an unfinished delivery.
        shutdown_delivery = MemoryDelivery(
            _envelope({"sku": "A-2", "revision": EXACT_REVISION + 1, "mode": "block"}),
            events=events,
        )
        shutdown_source = MemorySource([shutdown_delivery])
        stop_event = asyncio.Event()
        async with asyncio.TaskGroup() as group:
            consumer = group.create_task(
                consume_inbound_events(
                    binding,
                    container,
                    shutdown_source,
                    budgets=ConsumerBudgets(attempt_seconds=5.0, shutdown_seconds=0.02),
                    stop_event=stop_event,
                )
            )
            await entered_block.wait()
            stop_event.set()
        shutdown_diags = consumer.result()
    finally:
        await container.aclose()
        events.append("container.close")

    return {
        "surface_count": len(exposures.on_surface(binding.surface)),
        "asyncapi": asyncapi_doc["asyncapi"],
        "diagnostics": [(d.outcome, d.settlement) for d in (*diags, *shutdown_diags)],
        "events": events,
        "doc": asyncapi_doc,
    }


def main() -> None:
    result = asyncio.run(demonstrate())
    print(f"asyncapi: {result['asyncapi']}")
    print(f"surfaces: {result['surface_count']}")
    for outcome, settlement in result["diagnostics"]:
        print(f"{outcome}: {settlement}")
    print(f"events: {result['events']}")


if __name__ == "__main__":
    main()
