"""Application-owned SQLAlchemy/SQLite boundary; Agnara imports neither."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Integer, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from agnara import Agnara, App
from agnara.capability import CapabilityId
from agnara.core.di import DIContainer, DIRegistry, provider
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
)
from agnara.policy import Principal

_SCOPE = "persistence:write"
_WRITE = CapabilityId.parse("store.write")


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[int] = mapped_column(Integer)


class SQLiteStore:
    """An application port whose concrete transaction belongs to its host."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sessions_seen: list[Session] = []

    def add(self, value: int) -> None:
        self.sessions_seen.append(self.session)
        self.session.add(Record(value=value))


@dataclass
class Fixture:
    runtime: CapabilityRuntime
    container: DIContainer
    identifiers: dict[str, CapabilityId]


def runtime_for(
    session: Session,
    *,
    fail: bool = False,
    started: asyncio.Event | None = None,
    release: asyncio.Event | None = None,
) -> Fixture:
    """Bind the application store; Session never enters a core API surface."""

    store = SQLiteStore(session)
    registry = DIRegistry()

    @provider()
    def provide_store() -> Iterator[SQLiteStore]:
        yield store

    registry.bind(SQLiteStore, provide_store)
    project, app = Agnara("persistence"), App("store")

    @app.capability(scopes=(_SCOPE,))
    def write(value: int, store: SQLiteStore) -> int:
        store.add(value)
        if fail:
            raise RuntimeError("host must roll back")
        return value

    @app.capability(scopes=(_SCOPE,))
    async def nested(value: int, invoker: CapabilityInvoker, store: SQLiteStore) -> int:
        result = await invoker.invoke(_WRITE, {"value": value})
        assert isinstance(result, Success)
        assert store.sessions_seen[-1] is session
        return result.value

    @app.capability(scopes=(_SCOPE,))
    async def delayed(value: int, store: SQLiteStore) -> int:
        assert started is not None and release is not None
        started.set()
        await release.wait()
        store.add(value)
        return value

    project.include(app)
    capabilities = project.compile()
    container = DIContainer(registry)
    return Fixture(
        CapabilityRuntime(
            capabilities,
            [ExecutionPlan.compile(capability, registry) for capability in capabilities.values()],
            container,
        ),
        container,
        {str(capability_id): capability.id for capability_id, capability in capabilities.items()},
    )


def context_for(
    fixture: Fixture,
    identifier: CapabilityId,
    payload: dict[str, object],
    *,
    principal: Principal | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        Invocation(identifier, payload, {}), fixture.container, principal=principal
    )


async def invoke(
    fixture: Fixture,
    name: str,
    payload: dict[str, object],
    *,
    principal: Principal | None = None,
) -> object:
    return await fixture.runtime.invoke_result(
        context_for(fixture, fixture.identifiers[f"store.{name}"], payload, principal=principal)
    )


async def close(fixture: Fixture) -> None:
    await fixture.runtime.aclose()


def test_host_owns_sqlite_commit_and_rollback_around_canonical_results() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    writer = Principal("writer", scopes=(_SCOPE,))

    with Session(engine) as session:
        fixture = runtime_for(session)
        assert isinstance(
            asyncio.run(invoke(fixture, "write", {"value": 7}, principal=writer)), Success
        )
        session.commit()
        assert session.scalars(select(Record.value)).all() == [7]
        asyncio.run(close(fixture))

    with Session(engine) as session:
        fixture = runtime_for(session, fail=True)
        assert not isinstance(
            asyncio.run(invoke(fixture, "write", {"value": 9}, principal=writer)), Success
        )
        session.rollback()
        assert session.scalars(select(Record.value)).all() == [7]
        asyncio.run(close(fixture))
    engine.dispose()


def test_validation_and_policy_failures_do_not_open_a_persistence_transaction() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    writer = Principal("writer", scopes=(_SCOPE,))
    with Session(engine) as session:
        fixture = runtime_for(session)
        assert not isinstance(
            asyncio.run(invoke(fixture, "write", {"value": "bad"}, principal=writer)), Success
        )
        assert not isinstance(asyncio.run(invoke(fixture, "write", {"value": 8})), Success)
        assert session.scalars(select(Record.value)).all() == []
        asyncio.run(close(fixture))
    engine.dispose()


def test_cancellation_leaves_commit_or_rollback_to_the_host() -> None:
    async def run() -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        writer = Principal("writer", scopes=(_SCOPE,))
        started, release = asyncio.Event(), asyncio.Event()
        with Session(engine) as session:
            fixture = runtime_for(session, started=started, release=release)
            task = asyncio.create_task(invoke(fixture, "delayed", {"value": 5}, principal=writer))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            session.rollback()
            assert session.scalars(select(Record.value)).all() == []
            await close(fixture)
        engine.dispose()

    asyncio.run(run())


def test_nested_capability_reuses_the_application_owned_session() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    writer = Principal("writer", scopes=(_SCOPE,))
    with Session(engine) as session:
        fixture = runtime_for(session)
        assert isinstance(
            asyncio.run(invoke(fixture, "nested", {"value": 3}, principal=writer)), Success
        )
        session.commit()
        assert session.scalars(select(Record.value)).all() == [3]
        asyncio.run(close(fixture))
    engine.dispose()


def test_parallel_host_sessions_are_isolated(tmp_path: Path) -> None:
    async def run() -> None:
        engine = create_engine(f"sqlite:///{tmp_path / 'parallel.sqlite3'}")
        Base.metadata.create_all(engine)
        writer = Principal("writer", scopes=(_SCOPE,))
        with Session(engine) as first, Session(engine) as second:
            first_fixture, second_fixture = runtime_for(first), runtime_for(second)
            results = await asyncio.gather(
                invoke(first_fixture, "write", {"value": 1}, principal=writer),
                invoke(second_fixture, "write", {"value": 2}, principal=writer),
            )
            assert all(isinstance(result, Success) for result in results)
            first.commit()
            second.rollback()
            await close(first_fixture)
            await close(second_fixture)
        with Session(engine) as read:
            assert read.scalars(select(Record.value)).all() == [1]
        engine.dispose()

    asyncio.run(run())
