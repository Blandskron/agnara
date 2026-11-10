"""Runnable deadline tutorial preserves cancellation and resource ownership."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from examples.deadlines import demonstrate

from agnara.di import DIContainer
from agnara.execution import Failure, FailureCode, Success


def test_deadline_example_outcomes_cleanup_and_owned_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[DIContainer] = []
    original = DIContainer.aclose

    async def record_close(self: DIContainer) -> None:
        await original(self)
        closed.append(self)

    monkeypatch.setattr(DIContainer, "aclose", record_close)

    async def run() -> None:
        before = asyncio.all_tasks()
        results, events = await demonstrate()
        assert results["success"] == Success("done")
        denied = results["denied"]
        assert isinstance(denied, Failure) and denied.code is FailureCode.FORBIDDEN
        assert results["timeout"] == Failure(FailureCode.TIMEOUT, "invocation deadline exceeded")
        assert results["cancelled"] == "CancelledError"
        # Success, expired deadline and caller cancellation all finish their
        # handler and provider scope. The denied call acquires no resource.
        assert (
            events
            == [
                "session.open",
                "handler.enter",
                "handler.exit",
                "session.close",
            ]
            * 3
        )
        assert len(closed) == 1
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_deadline_example_preserves_owner_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    original_create = asyncio.TaskGroup.create_task
    original_close = DIContainer.aclose
    closed: list[DIContainer] = []

    def cancel_owner(self, coro, **kwargs):
        owner = asyncio.current_task()
        assert owner is not None
        task = original_create(self, coro, **kwargs)
        # Deliver owner cancellation as the cancelled child finishes, before
        # the example's await resumes. It must not become a demo outcome.
        task.add_done_callback(lambda _: owner.cancel())
        return task

    async def record_close(self: DIContainer) -> None:
        await original_close(self)
        closed.append(self)

    monkeypatch.setattr(asyncio.TaskGroup, "create_task", cancel_owner)
    monkeypatch.setattr(DIContainer, "aclose", record_close)

    async def run() -> None:
        before = asyncio.all_tasks()
        with pytest.raises(asyncio.CancelledError):
            await demonstrate()
        assert len(closed) == 1
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_deadline_example_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "deadlines.py"
    completed = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines()[:4] == [
        "success: done",
        "denied: forbidden",
        "timeout: timeout",
        "cancelled: CancelledError",
    ]
    assert len(completed.stdout.splitlines()) == 5
    assert completed.stdout.splitlines()[4] == "events: " + repr(
        ["session.open", "handler.enter", "handler.exit", "session.close"] * 3
    )
