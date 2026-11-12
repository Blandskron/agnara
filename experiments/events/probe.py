"""Run the EVT-01 inventory fixture against a dedicated RabbitMQ instance."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import sqlite3
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import closing
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Literal

from experiments.pydantic_schema_adapter import PydanticSchemaAdapter
from pydantic import Field

from agnara import Agnara, Principal, StandardSchemaAdapter
from agnara.di import DIContainer, DIRegistry, provider
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    invoke_result,
)

EVENT_TYPE = "example.inventory.snapshot.v1"
CONTENT_TYPE = "application/cloudevents+json"
SCOPE = "inventory:write"
EXACT_REVISION = 9007199254740993
type Sku = Annotated[str, Field(min_length=1)]
type Revision = Annotated[int, Field(ge=1, le=2**63 - 1)]
type Units = Annotated[int, Field(ge=0)]
type Outcome = Literal["applied", "unchanged", "conflict"]


class Inventory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.before_commit: asyncio.Event | None = None
        self.entered_commit = asyncio.Event()
        self.transient_failure = False
        self.open_connections = 0
        self.acquisitions = 0
        with closing(self.connect()) as connection:
            connection.executescript(
                "CREATE TABLE inventory (sku TEXT PRIMARY KEY, revision INTEGER, units TEXT);"
                "CREATE TABLE writes (revision INTEGER);"
            )

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def snapshot(self) -> tuple[list[tuple[str, int, int]], list[int]]:
        connection = self.connect()
        try:
            rows = connection.execute("SELECT * FROM inventory ORDER BY sku").fetchall()
            writes = connection.execute("SELECT revision FROM writes ORDER BY rowid").fetchall()
            return [(sku, revision, int(units)) for sku, revision, units in rows], [
                revision for (revision,) in writes
            ]
        finally:
            connection.close()

    def compose(self) -> tuple[ExecutionPlan, DIContainer]:
        app = Agnara("inventory")

        @provider()
        async def open_store() -> AsyncIterator[sqlite3.Connection]:
            connection = self.connect()
            self.open_connections += 1
            self.acquisitions += 1
            try:
                yield connection
            finally:
                connection.close()
                self.open_connections -= 1

        @app.capability(scopes=(SCOPE,), output=Outcome)
        async def apply(
            sku: Sku, revision: Revision, available_units: Units, store: sqlite3.Connection
        ) -> Outcome:
            if self.transient_failure:
                raise RuntimeError("fixture transient failure")
            units = str(available_units)
            store.execute("BEGIN IMMEDIATE")
            previous = store.execute(
                "SELECT revision, units FROM inventory WHERE sku = ?", (sku,)
            ).fetchone()
            if previous is not None and revision <= previous[0]:
                return (
                    "conflict" if revision == previous[0] and units != previous[1] else "unchanged"
                )
            store.execute(
                "INSERT INTO inventory VALUES (?, ?, ?) "
                "ON CONFLICT(sku) DO UPDATE SET revision=excluded.revision, units=excluded.units",
                (sku, revision, units),
            )
            store.execute("INSERT INTO writes VALUES (?)", (revision,))
            if self.before_commit is not None:
                self.entered_commit.set()
                await self.before_commit.wait()
            store.commit()
            return "applied"

        dependencies = DIRegistry()
        dependencies.bind(sqlite3.Connection, open_store)
        plan = ExecutionPlan.compile(
            app.compile()["inventory.apply"], dependencies, schema_adapter=PydanticSchemaAdapter()
        )
        return plan, DIContainer(dependencies)


def check_draft7(plan: ExecutionPlan) -> None:
    validator = import_module("jsonschema").Draft7Validator
    schema = {
        "type": "object",
        "properties": {name: item.json_schema() for name, item in plan.input_schemas.items()},
        "required": list(plan.input_schemas),
        "additionalProperties": False,
    }
    validator.check_schema(schema)
    inventory = validator(schema)
    valid = {"sku": "A-1", "revision": EXACT_REVISION, "available_units": 3}
    assert inventory.is_valid(valid)
    for change in INVALID_INPUTS:
        assert not inventory.is_valid({**valid, **change}), change
    assert inventory.is_valid({**valid, "revision": 2.0})

    tuple_schema = dict(StandardSchemaAdapter().compile(tuple[str, int]).json_schema())
    positions = tuple_schema.pop("prefixItems")
    assert tuple_schema["items"] is False
    draft7 = {**tuple_schema, "items": positions, "additionalItems": False}
    validator.check_schema(draft7)
    fixed_tuple = validator(draft7)
    assert fixed_tuple.is_valid(["A-1", 3])
    assert all(not fixed_tuple.is_valid(value) for value in (["A-1"], [3, "A-1"], ["A-1", 3, 0]))


INVALID_INPUTS = (
    {"sku": ""},
    {"revision": 0},
    {"revision": 2**63},
    {"revision": True},
    {"available_units": -1},
)


def payload(message: Any) -> dict[str, Any]:
    if message.content_type != CONTENT_TYPE or len(message.body) > 65536:
        raise ValueError("unsupported event content")
    event = json.loads(message.body.decode("utf-8"))
    if (
        not isinstance(event, dict)
        or event.get("type") != EVENT_TYPE
        or event.get("specversion") != "1.0"
        or not all(isinstance(event.get(key), str) and event[key] for key in ("source", "id"))
        or event.get("datacontenttype", "application/json") != "application/json"
        or not isinstance(event.get("data"), dict)
        or "data_base64" in event
    ):
        raise ValueError("unsupported event envelope")
    return event["data"]


async def settle(
    message: Any,
    plan: ExecutionPlan,
    container: DIContainer,
    principal: Principal,
    *,
    pause_ack: tuple[asyncio.Event, asyncio.Event] | None = None,
) -> str:
    try:
        inputs = payload(message)
    except ValueError:
        await message.reject(requeue=False)
        return "envelope"
    result = await invoke_result(
        plan,
        ExecutionContext(
            Invocation(plan.definition.id, inputs, {}), container, principal=principal
        ),
    )
    if isinstance(result, Failure):
        await message.reject(
            requeue=result.code
            in {
                FailureCode.INTERNAL_FAILURE,
                FailureCode.TIMEOUT,
                FailureCode.UNAVAILABLE,
                FailureCode.RATE_LIMITED,
            }
        )
        return result.code.value
    if result.value == "conflict":
        await message.reject(requeue=False)
    else:
        if pause_ack is not None:
            reached, resume = pause_ack
            reached.set()
            await resume.wait()
        await message.ack()
    return result.value


async def probe(inventory: Inventory) -> dict[str, Any]:
    amqp = import_module("aio_pika")
    access_refused = import_module("aiormq.exceptions").ChannelAccessRefused
    port = int(os.environ["AGNARA_EVT_PORT"])
    plan, container = inventory.compose()
    principal = Principal("inventory-consumer", scopes={SCOPE})

    async def connect(login: str):
        credential = os.environ["AGNARA_EVT_" + login.removeprefix("evt-").upper()]
        return await amqp.connect(host="127.0.0.1", port=port, login=login, password=credential)

    async def publish(
        exchange: Any,
        revision: int,
        *,
        event_id: str | None = None,
        units: int = 3,
        event_type: str = EVENT_TYPE,
        overrides: Mapping[str, object] | None = None,
    ) -> None:
        event = {
            "specversion": "1.0",
            "source": "/inventory",
            "id": event_id or str(revision),
            "type": event_type,
            "scope": SCOPE,
            "data": {
                "sku": "A-1",
                "revision": revision,
                "available_units": units,
                **(overrides or {}),
            },
        }
        await exchange.publish(
            amqp.Message(
                json.dumps(event).encode(),
                content_type=CONTENT_TYPE,
                delivery_mode=amqp.DeliveryMode.PERSISTENT,
            ),
            routing_key="snapshot",
        )

    try:
        check_draft7(plan)
        async with await connect("evt-admin") as admin, await connect("evt-publisher") as publisher:
            setup = await admin.channel()
            incoming = await setup.declare_exchange("inventory-in", durable=True)
            failed = await setup.declare_exchange("inventory-failed", durable=True)
            dead = await setup.declare_queue("inventory-dead", durable=True)
            await dead.bind(failed, routing_key="snapshot")
            queue = await setup.declare_queue(
                "inventory",
                durable=True,
                arguments={
                    "x-queue-type": "quorum",
                    "x-delivery-limit": 2,
                    "x-dead-letter-exchange": "inventory-failed",
                    "x-overflow": "reject-publish",
                },
            )
            await queue.bind(incoming, routing_key="snapshot")
            exchange = await (await publisher.channel()).get_exchange("inventory-in", ensure=False)

            async with await connect("evt-denied") as denied:
                denied_exchange = await (await denied.channel()).get_exchange(
                    "inventory-in", ensure=False
                )
                try:
                    await publish(denied_exchange, 1)
                except access_refused:
                    pass
                else:
                    raise AssertionError("publisher ACL allowed a forbidden publish")

            async def dead_letter(reason: str) -> None:
                while (message := await dead.get(fail=False, no_ack=False)) is None:
                    await asyncio.sleep(0.02)
                assert message.headers["x-first-death-reason"] == reason, message.headers
                await message.ack()

            # Losing the delivery channel after commit simulates interruption before ack.
            interrupted = await admin.channel()
            await interrupted.set_qos(prefetch_count=1)
            first_queue = await interrupted.get_queue("inventory", ensure=False)
            await publish(exchange, EXACT_REVISION)
            async with first_queue.iterator(no_ack=False) as deliveries:
                first = await anext(deliveries)
                inventory.before_commit = asyncio.Event()
                ready_to_ack = asyncio.Event()
                async with asyncio.TaskGroup() as group:
                    call = group.create_task(
                        settle(
                            first,
                            plan,
                            container,
                            principal,
                            pause_ack=(ready_to_ack, asyncio.Event()),
                        )
                    )
                    await inventory.entered_commit.wait()
                    assert not first.processed and inventory.snapshot() == ([], [])
                    inventory.before_commit.set()
                    await ready_to_ack.wait()
                    assert not first.processed
                    assert inventory.snapshot() == ([("A-1", EXACT_REVISION, 3)], [EXACT_REVISION])
                    call.cancel()
                assert call.cancelled()
                inventory.before_commit = None
                await interrupted.close()

            worker = await admin.channel()
            await worker.set_qos(prefetch_count=1)
            subscription = await worker.get_queue("inventory", ensure=False)
            async with subscription.iterator(no_ack=False) as deliveries:
                replay = await anext(deliveries)
                assert replay.redelivered and replay.headers["x-delivery-count"] == 1
                assert await settle(replay, plan, container, principal) == "unchanged"
                assert inventory.snapshot() == ([("A-1", EXACT_REVISION, 3)], [EXACT_REVISION])

                await publish(exchange, 1)
                assert (
                    await settle(await anext(deliveries), plan, container, principal) == "unchanged"
                )
                await publish(exchange, EXACT_REVISION, event_id="conflict", units=4)
                assert (
                    await settle(await anext(deliveries), plan, container, principal) == "conflict"
                )
                await dead_letter("rejected")

                prior_acquisitions = inventory.acquisitions
                await publish(exchange, 2, event_type="wrong")
                assert (
                    await settle(await anext(deliveries), plan, container, principal) == "envelope"
                )
                await dead_letter("rejected")
                for index, change in enumerate((*INVALID_INPUTS, {"revision": 2.0})):
                    await publish(exchange, 2, event_id=f"invalid-{index}", overrides=change)
                    assert (
                        await settle(await anext(deliveries), plan, container, principal)
                        == "invalid_input"
                    )
                    await dead_letter("rejected")
                await publish(exchange, 2, event_id="missing-scope")
                assert (
                    await settle(await anext(deliveries), plan, container, Principal("unscoped"))
                    == "forbidden"
                )
                await dead_letter("rejected")
                assert inventory.acquisitions == prior_acquisitions
                assert inventory.snapshot()[1] == [EXACT_REVISION]

                await publish(exchange, EXACT_REVISION + 1, event_id=str(EXACT_REVISION))
                assert (
                    await settle(await anext(deliveries), plan, container, principal) == "applied"
                )

                inventory.transient_failure = True
                await publish(exchange, EXACT_REVISION + 2, event_id="transient")
                counts = []
                for _ in range(3):
                    attempt = await anext(deliveries)
                    counts.append(attempt.headers.get("x-delivery-count", 0))
                    assert await settle(attempt, plan, container, principal) == "internal_failure"
                await dead_letter("delivery_limit")
                assert counts == [0, 1, 2], counts
                inventory.transient_failure = False

                await publish(exchange, EXACT_REVISION + 2, event_id="shutdown", units=2**63)
                unfinished = await anext(deliveries)
                inventory.before_commit = asyncio.Event()
                inventory.entered_commit.clear()
                async with asyncio.TaskGroup() as group:
                    task = group.create_task(settle(unfinished, plan, container, principal))
                    await inventory.entered_commit.wait()
                    task.cancel()
                assert task.cancelled() and inventory.open_connections == 0
                assert not unfinished.processed
                assert inventory.snapshot()[1] == [EXACT_REVISION, EXACT_REVISION + 1]
            # Stop receiving before release so the closing iterator cannot requeue it again.
            await unfinished.reject(requeue=True)
            inventory.before_commit = None
            async with subscription.iterator(no_ack=False) as deliveries:
                released = await anext(deliveries)
                assert released.redelivered and released.headers["x-delivery-count"] == 1, (
                    released.headers
                )
                assert await settle(released, plan, container, principal) == "applied"
            assert inventory.snapshot() == (
                [("A-1", EXACT_REVISION + 2, 2**63)],
                [EXACT_REVISION, EXACT_REVISION + 1, EXACT_REVISION + 2],
            )
            return {"retry_counts": counts, "committed_revisions": inventory.snapshot()[1]}
    finally:
        await container.aclose()


async def main() -> None:
    with TemporaryDirectory(prefix="agnara-evt01-") as directory:
        async with asyncio.timeout(45):
            observed = await probe(Inventory(Path(directory) / "inventory.db"))
    pending = asyncio.all_tasks() - {asyncio.current_task()}
    assert not pending, pending
    print(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "sqlite": sqlite3.sqlite_version,
                "versions": {
                    name: version(name)
                    for name in ("agnara", "aio-pika", "aiormq", "jsonschema", "pydantic")
                },
                **observed,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
