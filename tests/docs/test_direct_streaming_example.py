"""The direct streaming tutorial demonstrates demand and owns every resource."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from examples.direct_streaming import demonstrate, run_case

from agnara.di import DIContainer
from agnara.execution import FailureCode, StreamTerminal


def test_direct_streaming_outcomes_and_demand(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[DIContainer] = []
    original = DIContainer.aclose

    async def record_close(self: DIContainer) -> None:
        await original(self)
        closed.append(self)

    monkeypatch.setattr(DIContainer, "aclose", record_close)

    async def run() -> None:
        before = asyncio.all_tasks()
        outcomes = await demonstrate()
        success = outcomes["completed"]
        assert success.units == (0, 1)
        assert success.terminal is StreamTerminal.COMPLETED
        assert success.failure is None and success.refusal is None
        assert success.units_emitted == 2
        assert success.events == (
            "consumer.created",
            "session.open",
            "consumer.entered",
            "producer.open",
            "produce:0",
            "consume:0",
            "produce:1",
            "consume:1",
            "producer.close",
            "session.close",
        )
        abandoned = outcomes["abandoned"]
        assert abandoned.units == (0,)
        assert abandoned.terminal is StreamTerminal.ABANDONED
        assert abandoned.failure is None and abandoned.refusal is None
        assert abandoned.units_emitted == 1
        assert abandoned.events == success.events[:6] + success.events[-2:]
        for mode, refusal in (("denied", "forbidden"), ("invalid_input", "invalid_input")):
            result = outcomes[mode]
            assert result.refusal == refusal
            assert result.units == () and result.units_emitted == 0
            assert result.failure is None and result.terminal is None
            assert result.events == ("consumer.created",)
        for mode, units in (
            ("first_failure", ()),
            ("late_failure", (0,)),
            ("invalid_output", (0,)),
        ):
            result = outcomes[mode]
            assert result.units == units and result.units_emitted == len(units)
            assert result.terminal is StreamTerminal.INTERRUPTED
            assert result.failure is not None
            assert result.failure.code is FailureCode.INTERNAL_FAILURE
            assert "demo-private" not in repr(result.failure)
            assert result.refusal is None
            assert result.events[-2:] == ("producer.close", "session.close")
            assert result.events.count("session.open") == 1
            assert result.events.count("session.close") == 1
            assert "consume:1" not in result.events
        assert len(closed) == len(outcomes)
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_direct_streaming_cancellation_propagates_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[DIContainer] = []
    original = DIContainer.aclose

    async def record_close(self: DIContainer) -> None:
        await original(self)
        closed.append(self)

    monkeypatch.setattr(DIContainer, "aclose", record_close)

    async def run() -> None:
        before = asyncio.all_tasks()
        waiting = asyncio.Event()
        events: list[str] = []
        # The watchdog is a test bound, separate from invocation semantics.
        async with asyncio.timeout(5), asyncio.TaskGroup() as owned:
            task = owned.create_task(run_case("cancelled", waiting=waiting, events=events))
            await waiting.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert task.cancelled()
        assert len(closed) == 1
        assert events == [
            "consumer.created",
            "session.open",
            "consumer.entered",
            "producer.open",
            "producer.close",
            "session.close",
        ]
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_direct_streaming_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "direct_streaming.py"
    completed = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "completed: units=[0, 1] terminal=completed failure=None",
        "abandoned: units=[0] terminal=abandoned failure=None",
        "denied: units=[] terminal=not_started failure=forbidden",
        "invalid_input: units=[] terminal=not_started failure=invalid_input",
        "first_failure: units=[] terminal=interrupted failure=internal_failure",
        "late_failure: units=[0] terminal=interrupted failure=internal_failure",
        "invalid_output: units=[0] terminal=interrupted failure=internal_failure",
    ]
