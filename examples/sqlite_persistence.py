"""Host-owned SQLite transactions around canonical Agnara outcomes.

Run: uv run python examples/sqlite_persistence.py
SQLAlchemy is an optional application dependency; see docs/SQLITE_PERSISTENCE.md.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    CanonicalResult,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
)


class Ledger(Protocol):
    """Application port. Domain handlers know neither SQL nor Session."""

    def record(self, value: str) -> str: ...


class SqliteLedger:
    """Infrastructure implementation; transaction decisions belong to its owner."""

    def __init__(self, session: Session, events: list[str]) -> None:
        self._session = session
        self._events = events

    def record(self, value: str) -> str:
        self._session.execute(text("insert into entries (value) values (:value)"), {"value": value})
        self._events.append(f"write:{value}")
        return value


@dataclass
class Demonstration:
    results: dict[str, CanonicalResult | str]
    persisted: tuple[str, ...]
    events: list[str]


@contextmanager
def owned_session(engine: Engine, events: list[str]) -> Iterator[Session]:
    events.append("session.open")
    try:
        with Session(engine) as session:
            yield session
    finally:
        events.append("session.close")


def build_application(started: asyncio.Event) -> Agnara:
    app = Agnara("ledger")

    @app.capability(scopes={"ledger:write"}, effects={"database-write"}, output=str)
    def record(value: str, ledger: Ledger) -> str:
        return ledger.record(value)

    @app.capability(scopes={"ledger:write"}, effects={"database-write"}, output=str)
    def fail(value: str, ledger: Ledger) -> str:
        ledger.record(value)
        raise RuntimeError("private persistence fixture diagnostic")

    @app.capability(scopes={"ledger:write"}, effects={"database-write"}, output=str)
    async def wait(value: str, ledger: Ledger) -> str:
        ledger.record(value)
        started.set()
        await asyncio.Event().wait()
        return value

    return app


async def demonstrate() -> Demonstration:
    """Sequential transactions over one session, runtime and owning event loop."""
    events: list[str] = []
    results: dict[str, CanonicalResult | str] = {}
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("create table entries (value text not null)"))

        with owned_session(engine, events) as session:
            started = asyncio.Event()
            app = build_application(started)
            capabilities = app.compile()
            dependencies = DIRegistry()

            @provider(scope=Scope.INVOCATION)
            def provide_ledger() -> Iterator[Ledger]:
                events.append("port.open")
                try:
                    yield SqliteLedger(session, events)
                finally:
                    # The provider owns the port wrapper, not the host session.
                    events.append("port.close")

            dependencies.bind(Ledger, provide_ledger)
            plans = [ExecutionPlan.compile(item, dependencies) for item in capabilities.values()]
            container = DIContainer(dependencies)
            runtime = CapabilityRuntime(capabilities, plans, container)
            writer = Principal("demo-writer", scopes={"ledger:write"})

            async def transaction(
                name: str, payload: dict[str, object], principal: Principal = writer
            ) -> CanonicalResult:
                definition = capabilities[f"ledger.{name}"]
                try:
                    outcome = await runtime.invoke_result(
                        ExecutionContext(
                            Invocation(definition.id, payload, {}), container, principal=principal
                        )
                    )
                    # Canonical failures are values, so an exception-only
                    # transaction context would accidentally commit them.
                    if isinstance(outcome, Success):
                        session.commit()
                        events.append("host.commit")
                    else:
                        session.rollback()
                        events.append("host.rollback")
                    return outcome
                except BaseException:
                    # Includes caller cancellation and a failing host commit.
                    session.rollback()
                    events.append("host.rollback")
                    raise

            try:
                async with asyncio.timeout(5):
                    results["success"] = await transaction("record", {"value": "committed"})
                    results["denied"] = await transaction(
                        "record", {"value": "denied"}, Principal("unscoped")
                    )
                    results["invalid"] = await transaction("record", {"value": 42})
                    results["failed"] = await transaction("fail", {"value": "rolled-back"})
                    async with asyncio.TaskGroup() as owned:
                        caller = asyncio.current_task()
                        assert caller is not None
                        task = owned.create_task(transaction("wait", {"value": "cancelled"}))
                        await started.wait()
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            if caller.cancelling():
                                raise
                            results["cancelled"] = "CancelledError"
                        else:
                            raise AssertionError("cancellation must propagate")
                    assert task.cancelled()
            finally:
                # All owned calls have drained before runtime/session shutdown.
                await runtime.aclose()
                events.append("runtime.close")

        # A fresh observer proves committed storage, not an identity-map value.
        with Session(engine) as observer:
            persisted = tuple(observer.scalars(text("select value from entries order by rowid")))
        return Demonstration(results, persisted, events)
    finally:
        engine.dispose()
        events.append("engine.dispose")


def main() -> None:
    demo = asyncio.run(demonstrate())
    for name, result in demo.results.items():
        if isinstance(result, Success):
            print(f"{name}: {result.value}")
        elif isinstance(result, str):
            print(f"{name}: {result}")
        else:
            print(f"{name}: {result.code.value}")
    print(f"persisted: {demo.persisted}")
    print(f"events: {demo.events}")


if __name__ == "__main__":
    main()
