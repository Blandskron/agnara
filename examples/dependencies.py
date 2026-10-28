"""Explicit dependency bindings and owned resource lifetimes.

Run with ``uv run python examples/dependencies.py``. See docs/DEPENDENCIES.md.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    CanonicalResult,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    Success,
    invoke_result,
)


@dataclass
class Pool:
    """Local lifecycle fixture, not a database pool."""

    closed: bool = False


@dataclass
class Session:
    pool: Pool
    closed: bool = False


@dataclass
class Reader:
    session: Session
    closed: bool = False


@dataclass
class Writer:
    session: Session


@dataclass
class Demonstration:
    results: dict[str, CanonicalResult] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    # Retain fixture objects only so tests can inspect identity and closure.
    sessions: list[Session] = field(default_factory=list)
    readers: list[Reader] = field(default_factory=list)
    writers: list[Writer] = field(default_factory=list)
    pools: list[Pool] = field(default_factory=list)


async def demonstrate() -> Demonstration:
    demo = Demonstration()
    app = Agnara("storage")

    @provider(scope=Scope.SINGLETON)
    def provide_pool() -> Iterator[Pool]:
        pool = Pool()
        demo.pools.append(pool)
        demo.events.append("pool.open")
        try:
            yield pool
        finally:
            pool.closed = True
            demo.events.append("pool.close")

    @provider(scope=Scope.INVOCATION)
    async def provide_session(pool: Pool) -> AsyncIterator[Session]:
        session = Session(pool)
        demo.sessions.append(session)
        demo.events.append("session.open")
        try:
            yield session
        finally:
            session.closed = True
            demo.events.append("session.close")

    @provider(scope=Scope.INVOCATION)
    def provide_reader(session: Session) -> Iterator[Reader]:
        reader = Reader(session)
        demo.readers.append(reader)
        demo.events.append("reader.open")
        try:
            yield reader
        finally:
            reader.closed = True
            demo.events.append("reader.close")

    @provider(scope=Scope.INVOCATION)
    async def provide_writer(session: Session) -> Writer:
        writer = Writer(session)
        demo.writers.append(writer)
        return writer

    @app.capability(scopes=("storage:write",), output=str)
    def work(label: str, fail: bool, reader: Reader, writer: Writer) -> str:
        # The two provider branches share one session within this call.
        assert reader.session is writer.session
        assert not reader.closed and not reader.session.closed
        assert not reader.session.pool.closed
        demo.events.append("handler.enter")
        if fail:
            raise RuntimeError("private fixture diagnostic")
        return label

    dependencies = DIRegistry()
    dependencies.bind(Pool, provide_pool)
    dependencies.bind(Session, provide_session)
    dependencies.bind(Reader, provide_reader)
    dependencies.bind(Writer, provide_writer)
    plan = ExecutionPlan.compile(app.compile()["storage.work"], dependencies)
    container = DIContainer(dependencies)
    actor = Principal("local-demo", scopes={"storage:write"})

    async def call(payload: dict[str, object], principal: Principal = actor) -> CanonicalResult:
        return await invoke_result(
            plan,
            ExecutionContext(
                Invocation(plan.definition.id, payload, {}), container, principal=principal
            ),
        )

    try:
        async with asyncio.timeout(5):
            # These calls run before any resource has been acquired.
            demo.results["denied"] = await call(
                {"label": "denied", "fail": False}, Principal("unscoped")
            )
            demo.results["invalid"] = await call({"label": 42, "fail": False})
            assert not demo.events
            demo.results["first"] = await call({"label": "first", "fail": False})
            demo.results["second"] = await call({"label": "second", "fail": False})
            demo.results["failed"] = await call({"label": "failed", "fail": True})
            assert len(demo.pools) == 1 and not demo.pools[0].closed
    finally:
        # Invocations have exited; the application owns singleton teardown.
        await container.aclose()
    return demo


def main() -> None:
    demo = asyncio.run(demonstrate())
    for name, result in demo.results.items():
        if isinstance(result, Success):
            print(f"{name}: {result.value}")
        elif isinstance(result, Failure):
            print(f"{name}: {result.code.value}")
    print(f"pools: {len(demo.pools)}; sessions: {len(demo.sessions)}")
    print(f"events: {demo.events}")


if __name__ == "__main__":
    main()
