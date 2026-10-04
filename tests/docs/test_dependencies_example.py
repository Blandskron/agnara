"""Dependency tutorial proves identity, ordering and ownership contracts."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from examples import dependencies

from agnara.di import DIContainer
from agnara.execution import Failure, FailureCode, Success

INVOCATION_EVENTS = [
    "session.open",
    "reader.open",
    "handler.enter",
    "reader.close",
    "session.close",
]


def test_dependency_example_reuse_isolation_cleanup_and_redaction(caplog) -> None:
    async def run() -> None:
        before = asyncio.all_tasks()
        demo = await dependencies.demonstrate()
        assert demo.results["first"] == Success("first")
        assert demo.results["second"] == Success("second")
        for name, code in (
            ("denied", FailureCode.FORBIDDEN),
            ("invalid", FailureCode.INVALID_INPUT),
            ("failed", FailureCode.INTERNAL_FAILURE),
        ):
            result = demo.results[name]
            assert isinstance(result, Failure) and result.code is code
            assert "private fixture diagnostic" not in result.message
        # Denied/invalid calls acquire nothing. The two successes and failure
        # each unwind reader before session; the singleton closes last.
        assert demo.events == ["pool.open", *INVOCATION_EVENTS * 3, "pool.close"]
        assert len(demo.pools) == 1 and demo.pools[0].closed
        assert len(demo.sessions) == len(demo.readers) == len(demo.writers) == 3
        assert len({id(session) for session in demo.sessions}) == 3
        for session, reader, writer in zip(demo.sessions, demo.readers, demo.writers, strict=True):
            assert session is reader.session is writer.session
            assert session.pool is demo.pools[0]
            assert session.closed and reader.closed
        assert asyncio.all_tasks() == before

    asyncio.run(run())
    assert "private fixture diagnostic" not in caplog.text


def test_dependency_example_closes_singleton_on_owner_cancellation(monkeypatch) -> None:
    original_call = dependencies.invoke_result
    original_close = DIContainer.aclose
    closed: list[DIContainer] = []
    calls = 0

    async def cancel_after_success(*args, **kwargs):
        nonlocal calls
        result = await original_call(*args, **kwargs)
        calls += 1
        if calls == 3:
            raise asyncio.CancelledError
        return result

    async def record_close(self: DIContainer) -> None:
        pools = list(self.singleton_cache.values())
        assert len(pools) == 1 and not pools[0].closed
        await original_close(self)
        assert pools[0].closed and not self.singleton_cache
        closed.append(self)

    monkeypatch.setattr(dependencies, "invoke_result", cancel_after_success)
    monkeypatch.setattr(DIContainer, "aclose", record_close)

    async def run() -> None:
        before = asyncio.all_tasks()
        with pytest.raises(asyncio.CancelledError):
            await dependencies.demonstrate()
        assert len(closed) == 1
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_dependency_example_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "dependencies.py"
    completed = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "denied: forbidden",
        "invalid: invalid_input",
        "first: first",
        "second: second",
        "failed: internal_failure",
        "pools: 1; sessions: 3",
        "events: " + repr(["pool.open", *INVOCATION_EVENTS * 3, "pool.close"]),
    ]
    assert "private fixture diagnostic" not in completed.stdout + completed.stderr
