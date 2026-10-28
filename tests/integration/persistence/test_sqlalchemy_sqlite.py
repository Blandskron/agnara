"""Application-owned SQLAlchemy/SQLite boundary; Agnara imports neither."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Engine, Integer, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from agnara import Agnara, App, CapabilityId, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
)

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
    events: list[tuple[str, int]]


class ResourceProbe:
    """Application resource marker; loop observations stay in host state."""


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
    events = [("runtime.open", id(asyncio.get_running_loop()))]

    @provider(scope=Scope.SINGLETON)
    async def resource_probe() -> AsyncIterator[ResourceProbe]:
        events.append(("resource.open", id(asyncio.get_running_loop())))
        try:
            yield ResourceProbe()
        finally:
            events.append(("resource.close", id(asyncio.get_running_loop())))

    registry.bind(ResourceProbe, resource_probe)

    @provider()
    def provide_store(probe: ResourceProbe) -> Iterator[SQLiteStore]:
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
        events,
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
    fixture.events.append(("invoke", id(asyncio.get_running_loop())))
    return await fixture.runtime.invoke_result(
        context_for(fixture, fixture.identifiers[f"store.{name}"], payload, principal=principal)
    )


async def close(fixture: Fixture) -> None:
    await fixture.runtime.aclose()
    fixture.events.append(("runtime.close", id(asyncio.get_running_loop())))


@asynccontextmanager
async def host_session(
    engine: Engine,
    *,
    fail: bool = False,
    started: asyncio.Event | None = None,
    release: asyncio.Event | None = None,
) -> AsyncIterator[tuple[Fixture, Session]]:
    """Drain calls in the scenario, then close runtime before the host session."""
    fixture = None
    try:
        with Session(engine) as session:
            fixture = runtime_for(session, fail=fail, started=started, release=release)
            try:
                yield fixture, session
            finally:
                await close(fixture)
    finally:
        if fixture is not None:
            fixture.events.append(("session.close", id(asyncio.get_running_loop())))


def assert_owned_cleanup(fixture: Fixture, *, resource_opened: bool = True) -> None:
    assert {loop for _, loop in fixture.events} == {fixture.events[0][1]}
    names = [name for name, _ in fixture.events]
    assert names[-2:] == ["runtime.close", "session.close"]
    if resource_opened:
        assert names.count("resource.open") == names.count("resource.close") == 1
        assert names[-3] == "resource.close"
    else:
        assert "resource.open" not in names and "resource.close" not in names


def test_host_owns_sqlite_commit_and_rollback_around_canonical_results() -> None:
    async def run() -> None:
        engine = create_engine("sqlite://")
        try:
            Base.metadata.create_all(engine)
            writer = Principal("writer", scopes=(_SCOPE,))
            async with host_session(engine) as (fixture, session):
                assert isinstance(
                    await invoke(fixture, "write", {"value": 7}, principal=writer), Success
                )
                session.commit()
                assert session.scalars(select(Record.value)).all() == [7]
            assert_owned_cleanup(fixture)

            async with host_session(engine, fail=True) as (fixture, session):
                assert not isinstance(
                    await invoke(fixture, "write", {"value": 9}, principal=writer), Success
                )
                session.rollback()
                assert session.scalars(select(Record.value)).all() == [7]
            assert_owned_cleanup(fixture)
        finally:
            engine.dispose()

    asyncio.run(run())


def test_validation_and_policy_failures_do_not_open_a_persistence_transaction() -> None:
    async def run() -> None:
        engine = create_engine("sqlite://")
        try:
            Base.metadata.create_all(engine)
            writer = Principal("writer", scopes=(_SCOPE,))
            async with host_session(engine) as (fixture, session):
                assert not isinstance(
                    await invoke(fixture, "write", {"value": "bad"}, principal=writer), Success
                )
                assert not isinstance(await invoke(fixture, "write", {"value": 8}), Success)
                assert not session.in_transaction()
                assert "resource.open" not in [name for name, _ in fixture.events]
                assert session.scalars(select(Record.value)).all() == []
            assert_owned_cleanup(fixture, resource_opened=False)
        finally:
            engine.dispose()

    asyncio.run(run())


def test_cancellation_leaves_commit_or_rollback_to_the_host() -> None:
    async def run() -> None:
        engine = create_engine("sqlite://")
        try:
            Base.metadata.create_all(engine)
            writer = Principal("writer", scopes=(_SCOPE,))
            started, release = asyncio.Event(), asyncio.Event()
            async with host_session(engine, started=started, release=release) as (fixture, session):
                async with asyncio.TaskGroup() as tasks:
                    task = tasks.create_task(
                        invoke(fixture, "delayed", {"value": 5}, principal=writer)
                    )
                    await started.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                session.rollback()
                assert session.scalars(select(Record.value)).all() == []
            assert_owned_cleanup(fixture)
        finally:
            engine.dispose()

    asyncio.run(run())


def test_nested_capability_reuses_the_application_owned_session() -> None:
    async def run() -> None:
        engine = create_engine("sqlite://")
        try:
            Base.metadata.create_all(engine)
            writer = Principal("writer", scopes=(_SCOPE,))
            async with host_session(engine) as (fixture, session):
                assert isinstance(
                    await invoke(fixture, "nested", {"value": 3}, principal=writer), Success
                )
                session.commit()
                assert session.scalars(select(Record.value)).all() == [3]
            assert_owned_cleanup(fixture)
        finally:
            engine.dispose()

    asyncio.run(run())


def test_parallel_host_sessions_are_isolated(tmp_path: Path) -> None:
    async def run() -> None:
        engine = create_engine(f"sqlite:///{tmp_path / 'parallel.sqlite3'}")
        try:
            Base.metadata.create_all(engine)
            writer = Principal("writer", scopes=(_SCOPE,))
            async with (
                host_session(engine) as (first_fixture, first),
                host_session(engine) as (second_fixture, second),
            ):
                async with asyncio.TaskGroup() as tasks:
                    first_call = tasks.create_task(
                        invoke(first_fixture, "write", {"value": 1}, principal=writer)
                    )
                    second_call = tasks.create_task(
                        invoke(second_fixture, "write", {"value": 2}, principal=writer)
                    )
                assert all(isinstance(call.result(), Success) for call in (first_call, second_call))
                first.commit()
                second.rollback()
            assert_owned_cleanup(first_fixture)
            assert_owned_cleanup(second_fixture)
            with Session(engine) as read:
                assert read.scalars(select(Record.value)).all() == [1]
        finally:
            engine.dispose()

    asyncio.run(run())


def test_exceptional_host_exit_closes_runtime_before_session_and_engine() -> None:
    async def run() -> None:
        engine = create_engine("sqlite://")
        try:
            Base.metadata.create_all(engine)
            writer = Principal("writer", scopes=(_SCOPE,))
            with pytest.raises(RuntimeError, match="host exit"):
                async with host_session(engine) as (fixture, session):
                    assert isinstance(
                        await invoke(fixture, "write", {"value": 4}, principal=writer), Success
                    )
                    assert session.in_transaction()
                    raise RuntimeError("host exit")
            assert_owned_cleanup(fixture)
            with Session(engine) as read:
                assert read.scalars(select(Record.value)).all() == []
        finally:
            engine.dispose()
        fixture.events.append(("engine.dispose", id(asyncio.get_running_loop())))
        assert [name for name, _ in fixture.events][-4:] == [
            "resource.close",
            "runtime.close",
            "session.close",
            "engine.dispose",
        ]
        assert {loop for _, loop in fixture.events} == {fixture.events[0][1]}

    asyncio.run(run())
