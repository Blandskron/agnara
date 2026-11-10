"""Persistence tutorial verifies real storage and host-owned cleanup."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from examples import sqlite_persistence as example
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from agnara.execution import CapabilityRuntime, Failure, FailureCode, Success


def test_host_commits_only_success_and_rolls_back_failure_and_cancellation(monkeypatch, caplog):
    original_engine = example.create_engine
    writes: list[object] = []

    def engine(*args, **kwargs):
        built = original_engine(*args, **kwargs)

        def record_sql(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("insert into entries"):
                writes.append(parameters)

        event.listen(built, "before_cursor_execute", record_sql)
        return built

    monkeypatch.setattr(example, "create_engine", engine)

    async def run() -> example.Demonstration:
        before = asyncio.all_tasks()
        demo = await example.demonstrate()
        assert asyncio.all_tasks() == before
        return demo

    demo = asyncio.run(run())
    assert demo.results["success"] == Success("committed")
    for name, code in (
        ("denied", FailureCode.FORBIDDEN),
        ("invalid", FailureCode.INVALID_INPUT),
        ("failed", FailureCode.INTERNAL_FAILURE),
    ):
        outcome = demo.results[name]
        assert isinstance(outcome, Failure) and outcome.code is code
        assert "private persistence fixture diagnostic" not in outcome.message
    assert demo.results["cancelled"] == "CancelledError"
    assert demo.persisted == ("committed",)
    assert writes == [("committed",), ("rolled-back",), ("cancelled",)]
    assert demo.events == [
        "session.open",
        "port.open",
        "write:committed",
        "port.close",
        "host.commit",
        "host.rollback",
        "host.rollback",
        "port.open",
        "write:rolled-back",
        "port.close",
        "host.rollback",
        "port.open",
        "write:cancelled",
        "port.close",
        "host.rollback",
        "runtime.close",
        "session.close",
        "engine.dispose",
    ]
    assert "private persistence fixture diagnostic" not in caplog.text


def test_output_contract_failure_is_rolled_back_by_host(monkeypatch):
    original_record = example.SqliteLedger.record

    def invalid_output(self, value):
        original_record(self, value)
        return 42

    monkeypatch.setattr(example.SqliteLedger, "record", invalid_output)
    demo = asyncio.run(example.demonstrate())
    result = demo.results["success"]
    assert isinstance(result, Failure) and result.code is FailureCode.INTERNAL_FAILURE
    assert demo.persisted == ()
    assert "host.commit" not in demo.events
    assert demo.events[-3:] == ["runtime.close", "session.close", "engine.dispose"]


def test_failing_host_commit_rolls_back_and_closes_on_owner_loop(monkeypatch):
    original_rollback = Session.rollback
    original_close = Session.close
    original_runtime_close = CapabilityRuntime.aclose
    original_dispose = Engine.dispose
    events: list[str] = []

    async def run() -> None:
        owner = asyncio.get_running_loop()
        before = asyncio.all_tasks()

        def commit(self):
            assert self.in_transaction()
            raise RuntimeError("host commit fixture failure")

        def rollback(self):
            assert asyncio.get_running_loop() is owner
            original_rollback(self)
            assert not self.in_transaction()
            events.append("rollback")

        async def runtime_close(self):
            assert asyncio.get_running_loop() is owner
            await original_runtime_close(self)
            events.append("runtime.close")

        def close(self):
            assert asyncio.get_running_loop() is owner
            original_close(self)
            events.append("session.close")

        def dispose(self, *args, **kwargs):
            assert asyncio.get_running_loop() is owner
            original_dispose(self, *args, **kwargs)
            events.append("engine.dispose")

        monkeypatch.setattr(Session, "commit", commit)
        monkeypatch.setattr(Session, "rollback", rollback)
        monkeypatch.setattr(CapabilityRuntime, "aclose", runtime_close)
        monkeypatch.setattr(Session, "close", close)
        monkeypatch.setattr(Engine, "dispose", dispose)
        with pytest.raises(RuntimeError, match="host commit fixture failure"):
            await example.demonstrate()
        assert events == ["rollback", "runtime.close", "session.close", "engine.dispose"]
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_cancelling_host_drains_child_and_closes_resources(monkeypatch):
    original_build = example.build_application
    original_ledger = example.SqliteLedger
    observed: list[list[str]] = []

    def ledger(session, events):
        observed.append(events)
        return original_ledger(session, events)

    monkeypatch.setattr(example, "SqliteLedger", ledger)

    async def run() -> None:
        ready: asyncio.Future[asyncio.Event] = asyncio.get_running_loop().create_future()

        def build(started):
            ready.set_result(started)
            return original_build(started)

        monkeypatch.setattr(example, "build_application", build)
        before = asyncio.all_tasks()
        async with asyncio.timeout(5), asyncio.TaskGroup() as owned:
            task = owned.create_task(example.demonstrate())
            started = await ready
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert task.cancelled()
        assert asyncio.all_tasks() == before

    asyncio.run(run())
    assert observed[-1][-5:] == [
        "port.close",
        "host.rollback",
        "runtime.close",
        "session.close",
        "engine.dispose",
    ]


def test_persistence_script_runs():
    completed = subprocess.run(
        [sys.executable, "examples/sqlite_persistence.py"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    for expected in (
        "success: committed",
        "denied: forbidden",
        "invalid: invalid_input",
        "failed: internal_failure",
        "cancelled: CancelledError",
        "persisted: ('committed',)",
    ):
        assert expected in completed.stdout
    assert "private persistence fixture diagnostic" not in completed.stdout + completed.stderr
