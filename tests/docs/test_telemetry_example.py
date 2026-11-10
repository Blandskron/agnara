"""The local telemetry guide pairs events without collecting runtime payloads."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import fields
from pathlib import Path

import pytest
from examples.invocation_telemetry import Recorder, demonstrate

from agnara import CapabilityId
from agnara.di import DIContainer
from agnara.execution import Failure, FailureCode, InvocationTerminalEvent, Success


def test_telemetry_example_pairs_all_outcomes_and_closes_container(
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
        results, recorder, faulty, effects = await demonstrate()
        assert results["success"] == Success("private-result")
        for name, code in (
            ("denied", FailureCode.FORBIDDEN),
            ("invalid", FailureCode.INVALID_INPUT),
            ("failed", FailureCode.INTERNAL_FAILURE),
            ("timeout", FailureCode.TIMEOUT),
        ):
            result = results[name]
            assert isinstance(result, Failure) and result.code is code
        assert results["cancelled"] == "CancelledError"
        assert effects == ["private-input", "fail", "wait", "wait"]
        assert faulty.starts == faulty.terminals == 6
        assert recorder.pending == {}
        assert [terminal.outcome for _, terminal in recorder.pairs] == [
            "success",
            "failure",
            "failure",
            "failure",
            "timeout",
            "cancellation",
        ]
        attempts: set[str] = set()
        executions: set[str] = set()
        for start, terminal in recorder.pairs:
            assert start is not None
            assert start.invocation_id == terminal.invocation_id
            assert start.execution_id == terminal.execution_id
            assert start.execution_id is not None
            assert start.capability_id == terminal.capability_id == CapabilityId.parse("jobs.work")
            assert start.tracking_id == terminal.tracking_id == "batch-demo"
            assert start.parent_execution_id is terminal.parent_execution_id is None
            assert terminal.units is None and terminal.duration_ns >= 0
            attempts.add(start.invocation_id)
            executions.add(start.execution_id)
            assert {field.name for field in fields(start)} == {
                "capability_id",
                "tracking_id",
                "invocation_id",
                "execution_id",
                "parent_execution_id",
            }
            assert {field.name for field in fields(terminal)} == {
                "capability_id",
                "tracking_id",
                "duration_ns",
                "outcome",
                "invocation_id",
                "units",
                "execution_id",
                "parent_execution_id",
            }
        assert len(attempts) == len(executions) == 6
        for private in (
            "private-input",
            "private-result",
            "private-handler-diagnostic",
            "private-observer-diagnostic",
        ):
            assert private not in repr(recorder.pairs)
        assert "private-handler-diagnostic" not in repr(results["failed"])
        assert len(closed) == 1
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_telemetry_recorder_tolerates_a_missing_start() -> None:
    recorder = Recorder()
    terminal = InvocationTerminalEvent(
        capability_id=CapabilityId.parse("jobs.work"),
        tracking_id="batch-demo",
        duration_ns=0,
        outcome="failure",
        invocation_id="missing-start",
    )
    recorder.on_invocation_terminal(terminal)
    assert recorder.pairs == [(None, terminal)]
    assert recorder.pending == {}


def test_telemetry_example_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "invocation_telemetry.py"
    completed = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "success: success; telemetry: success",
        "denied: forbidden; telemetry: failure",
        "invalid: invalid_input; telemetry: failure",
        "failed: internal_failure; telemetry: failure",
        "timeout: timeout; telemetry: timeout",
        "cancelled: CancelledError; telemetry: cancellation",
        "paired: 6; pending: 0; attempts: 6; correlation labels: 1",
    ]
    assert "private-handler-diagnostic" not in completed.stderr
    assert "private-observer-diagnostic" not in completed.stderr
