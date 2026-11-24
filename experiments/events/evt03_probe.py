"""Run the EVT-03 RabbitMQ 4.2.5 probe against internal agnara-events modules."""

from __future__ import annotations

import asyncio
import contextlib
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

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import ExecutionPlan, Failure, FailureCode
from agnara_events._asyncapi import _AsyncAPIInfo, _project_asyncapi
from agnara_events._consumer import (
    _consume_inbound_events,
    _ConsumerBudgets,
    _ConsumerDiagnostic,
    _Delivery,
)
from agnara_events._envelope import CLOUDEVENTS_JSON_CONTENT_TYPE, MAX_BODY_BYTES
from agnara_events._exposure import _compile_inbound_event, _declare_inbound_event

EVENT_TYPE = "example.inventory.snapshot.v1"
SCOPE = "inventory:write"
EXACT_REVISION = 9007199254740993
type Sku = Annotated[str, Field(min_length=1)]
type Revision = Annotated[int, Field(ge=1, le=2**63 - 1)]
type Units = Annotated[int, Field(ge=0)]
type Outcome = Literal["applied", "unchanged"]


class _RabbitMqDelivery:
    """Wrap an ``aio_pika`` incoming message behind the broker-neutral protocol."""

    def __init__(self, message: Any) -> None:
        self._message = message

    @property
    def body(self) -> bytes:
        return bytes(self._message.body)

    @property
    def content_type(self) -> str | None:
        return self._message.content_type

    async def acknowledge(self) -> None:
        await self._message.ack()

    async def reject(self) -> None:
        await self._message.reject(requeue=False)

    async def release(self) -> None:
        await self._message.reject(requeue=True)


class _RabbitMqDeliverySource:
    """Single-consumer ``aio_pika`` queue iterator wrapper."""

    def __init__(self, queue: Any) -> None:
        self._ctx = queue.iterator(no_ack=False)
        self._iterator: AsyncIterator[Any] | None = None
        self._stopped = False

    async def __aenter__(self) -> _RabbitMqDeliverySource:
        self._iterator = await self._ctx.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self._ctx.__aexit__(exc_type, exc, tb)

    async def receive(self) -> _Delivery | None:
        if self._stopped or self._iterator is None:
            return None
        try:
            message = await anext(self._iterator)
        except StopAsyncIteration:
            return None
        return _RabbitMqDelivery(message)

    async def stop_receiving(self) -> None:
        self._stopped = True


class Evt03Inventory:
    """SQLite inventory fixture reporting snapshot conflicts as Failure(CONFLICT)."""

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

    def compose(self) -> tuple[ExecutionPlan, DIContainer, Any]:
        app = Agnara("inventory")

        @provider(scope=Scope.INVOCATION)
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
        ) -> Outcome | Failure:
            if self.transient_failure:
                raise RuntimeError("fixture transient failure")
            units = str(available_units)
            store.execute("BEGIN IMMEDIATE")
            previous = store.execute(
                "SELECT revision, units FROM inventory WHERE sku = ?", (sku,)
            ).fetchone()
            if previous is not None and revision <= previous[0]:
                if revision == previous[0] and units != previous[1]:
                    return Failure(FailureCode.CONFLICT, "snapshot revision conflict")
                return "unchanged"
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

        compiled = app.compile()
        dependencies = DIRegistry()
        dependencies.bind(sqlite3.Connection, open_store)
        definition = compiled["inventory.apply"]
        plan = ExecutionPlan.compile(
            definition,
            dependencies,
            schema_adapter=PydanticSchemaAdapter(),
        )
        return plan, DIContainer(dependencies), definition


def validate_asyncapi_export(binding: Any) -> dict[str, Any]:
    validator_cls = import_module("jsonschema").Draft7Validator
    document = _project_asyncapi(
        binding,
        _AsyncAPIInfo(title="EVT-03 Inventory", version="1.0.0"),
    )
    schema = document["components"]["messages"]["inventory-applyMessage"]["payload"]["schema"]
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    valid = {
        "specversion": "1.0",
        "id": "1",
        "source": "/inventory",
        "type": EVENT_TYPE,
        "datacontenttype": "application/json",
        "data": {"sku": "A-1", "revision": EXACT_REVISION, "available_units": 3},
    }
    assert validator.is_valid(valid)
    assert validator.is_valid({**valid, "data": {**valid["data"], "revision": 2.0}})
    assert not validator.is_valid({**valid, "data": {**valid["data"], "available_units": -1}})
    return document


async def run_one_delivery(
    binding: Any,
    container: DIContainer,
    queue: Any,
    *,
    budgets: _ConsumerBudgets,
) -> _ConsumerDiagnostic:
    stop = asyncio.Event()
    recorded: list[_ConsumerDiagnostic] = []

    def stop_after_one(entry: _ConsumerDiagnostic) -> None:
        recorded.append(entry)
        stop.set()

    async with _RabbitMqDeliverySource(queue) as source:
        diags = await _consume_inbound_events(
            binding,
            container,
            source,
            budgets=budgets,
            stop_event=stop,
            on_diagnostic=stop_after_one,
        )
    assert len(diags) == 1
    return diags[0]


async def probe(inventory: Evt03Inventory) -> dict[str, Any]:
    amqp = import_module("aio_pika")
    access_refused = import_module("aiormq.exceptions").ChannelAccessRefused
    port = int(os.environ["AGNARA_EVT_PORT"])
    plan, container, definition = inventory.compose()
    principal = Principal("inventory-consumer", scopes={SCOPE})
    binding = _compile_inbound_event(
        _declare_inbound_event(
            definition,
            subscription_id="inventory-apply",
            event_type=EVENT_TYPE,
            principal=principal,
            public_address="inventory.snapshot.v1",
        ),
        {definition.id: plan},
    )
    validate_asyncapi_export(binding)

    async def connect(login: str) -> Any:
        credential = os.environ["AGNARA_EVT_" + login.removeprefix("evt-").upper()]
        return await amqp.connect(host="127.0.0.1", port=port, login=login, password=credential)

    async def publish_raw(
        exchange: Any,
        raw_body: bytes,
        *,
        content_type: str = CLOUDEVENTS_JSON_CONTENT_TYPE,
    ) -> None:
        await exchange.publish(
            amqp.Message(
                raw_body,
                content_type=content_type,
                delivery_mode=amqp.DeliveryMode.PERSISTENT,
            ),
            routing_key="snapshot",
        )

    async def publish_event(
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
            "data": {
                "sku": "A-1",
                "revision": revision,
                "available_units": units,
                **(overrides or {}),
            },
        }
        await publish_raw(exchange, json.dumps(event).encode("utf-8"))

    budgets = _ConsumerBudgets(attempt_seconds=5.0, shutdown_seconds=2.0)
    try:
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
                    await publish_event(denied_exchange, 1)
                except access_refused:
                    pass
                else:
                    raise AssertionError("publisher ACL allowed a forbidden publish")

            async def dead_letter(reason: str) -> None:
                while (message := await dead.get(fail=False, no_ack=False)) is None:
                    await asyncio.sleep(0.02)
                assert message.headers["x-first-death-reason"] == reason, message.headers
                await message.ack()

            worker = await admin.channel()
            await worker.set_qos(prefetch_count=1)
            subscription = await worker.get_queue("inventory", ensure=False)

            # 1. Valid snapshot with 53-bit+ exact integer revision.
            await publish_event(exchange, EXACT_REVISION)
            diag = await run_one_delivery(binding, container, subscription, budgets=budgets)
            assert diag.outcome == "success" and diag.settlement == "acknowledge"

            # 2. Canonical CONFLICT -> reject -> dead-letter without string parsing.
            await publish_event(exchange, EXACT_REVISION, event_id="conflict", units=4)
            conflict_diag = await run_one_delivery(
                binding, container, subscription, budgets=budgets
            )
            assert conflict_diag.outcome == "conflict" and conflict_diag.settlement == "reject"
            await dead_letter("rejected")

            # 3. Decoder rejections (>65,536 bytes, duplicate key, wrong type) + lexical 2.0.
            prior_acquisitions = inventory.acquisitions
            await publish_raw(exchange, b"{" + b" " * MAX_BODY_BYTES + b"}")
            assert (
                await run_one_delivery(binding, container, subscription, budgets=budgets)
            ).outcome == "body_too_large"
            await dead_letter("rejected")

            await publish_raw(
                exchange,
                (
                    b'{"specversion":"1.0","id":"dup","source":"/s","type":"'
                    + EVENT_TYPE.encode()
                    + b'","data":{"sku":"A-1","sku":"B-2","revision":2,"available_units":1}}'
                ),
            )
            assert (
                await run_one_delivery(binding, container, subscription, budgets=budgets)
            ).outcome == "duplicate_key"
            await dead_letter("rejected")

            await publish_event(exchange, 2, event_id="wrong-type", event_type="wrong.type")
            assert (
                await run_one_delivery(binding, container, subscription, budgets=budgets)
            ).outcome == "type_mismatch"
            await dead_letter("rejected")

            await publish_event(exchange, 2, event_id="float-rev", overrides={"revision": 2.0})
            assert (
                await run_one_delivery(binding, container, subscription, budgets=budgets)
            ).outcome == "invalid_input"
            await dead_letter("rejected")
            assert inventory.acquisitions == prior_acquisitions

            # 4. Bounded redelivery for transient internal failure -> dead-lettered at limit.
            inventory.transient_failure = True
            await publish_event(exchange, EXACT_REVISION + 1, event_id="transient")
            for _ in range(3):
                transient_diag = await run_one_delivery(
                    binding, container, subscription, budgets=budgets
                )
                assert (
                    transient_diag.outcome == "internal_failure"
                    and transient_diag.settlement == "release"
                )
            await dead_letter("delivery_limit")
            inventory.transient_failure = False

            # 5. Shutdown timeout cancels handler, closes SQLite, releases, then replays.
            await publish_event(exchange, EXACT_REVISION + 2, event_id="shutdown", units=2**63)
            inventory.before_commit = asyncio.Event()
            inventory.entered_commit.clear()
            stop_signal = asyncio.Event()
            async with _RabbitMqDeliverySource(subscription) as source:
                consumer_task = asyncio.create_task(
                    _consume_inbound_events(
                        binding,
                        container,
                        source,
                        budgets=_ConsumerBudgets(attempt_seconds=5.0, shutdown_seconds=0.05),
                        stop_event=stop_signal,
                    )
                )
                await inventory.entered_commit.wait()
                stop_signal.set()
                shutdown_diags = await consumer_task
            assert shutdown_diags[0].outcome == "cancelled"
            assert shutdown_diags[0].settlement == "release"
            assert inventory.open_connections == 0

            inventory.before_commit = None
            replayed_diag = await run_one_delivery(
                binding, container, subscription, budgets=budgets
            )
            assert replayed_diag.outcome == "success" and replayed_diag.settlement == "acknowledge"
            assert inventory.snapshot() == (
                [("A-1", EXACT_REVISION + 2, 2**63)],
                [EXACT_REVISION, EXACT_REVISION + 2],
            )
            return {
                "committed_revisions": inventory.snapshot()[1],
                "asyncapi_version": "3.1.0",
            }
    finally:
        with contextlib.suppress(Exception):
            await container.aclose()


async def main() -> None:
    with TemporaryDirectory(prefix="agnara-evt03-") as directory:
        async with asyncio.timeout(45):
            observed = await probe(Evt03Inventory(Path(directory) / "inventory.db"))
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
                    for name in ("agnara", "agnara-events", "aio-pika", "jsonschema", "pydantic")
                },
                **observed,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
