"""Check the exact local telemetry guide against candidate wheels under Python -I."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

from agnara import CapabilityId
from agnara.execution import (
    Failure,
    FailureCode,
    InvocationStartEvent,
    InvocationTerminalEvent,
    Success,
)


def validate(demo: Any) -> None:
    results, recorder, faulty, effects = demo
    assert list(results) == ["success", "denied", "invalid", "failed", "timeout", "cancelled"]
    assert results["success"] == Success("private-result")
    assert results["cancelled"] == "CancelledError"
    for name, code in (
        ("denied", FailureCode.FORBIDDEN),
        ("invalid", FailureCode.INVALID_INPUT),
        ("failed", FailureCode.INTERNAL_FAILURE),
        ("timeout", FailureCode.TIMEOUT),
    ):
        result = results[name]
        assert isinstance(result, Failure) and result.code is code
        assert "private" not in result.message + repr(result.details)
    assert results["invalid"].details["path"] == ("action",)
    assert results["failed"].message == "capability invocation failed"
    assert not results["failed"].details
    assert effects == ["private-input", "fail", "wait", "wait"]
    assert faulty.starts == faulty.terminals == 6
    assert not recorder.pending
    assert len(recorder.pairs) == 6
    outcomes = ["success", "failure", "failure", "failure", "timeout", "cancellation"]
    start_fields = {
        "capability_id",
        "tracking_id",
        "invocation_id",
        "execution_id",
        "parent_execution_id",
    }
    terminal_fields = start_fields | {"duration_ns", "outcome", "units"}
    attempts: set[str] = set()
    executions: set[str] = set()
    for (start, terminal), outcome in zip(recorder.pairs, outcomes, strict=True):
        assert type(start) is InvocationStartEvent and type(terminal) is InvocationTerminalEvent
        assert {field.name for field in fields(start)} == start_fields
        assert {field.name for field in fields(terminal)} == terminal_fields
        assert start.capability_id == terminal.capability_id == CapabilityId.parse("jobs.work")
        assert start.tracking_id == terminal.tracking_id == "batch-demo"
        assert start.invocation_id == terminal.invocation_id
        assert start.execution_id == terminal.execution_id
        assert type(start.invocation_id) is str and start.invocation_id
        assert type(start.execution_id) is str and start.execution_id
        assert start.parent_execution_id is terminal.parent_execution_id is None
        assert terminal.outcome == outcome and terminal.units is None
        assert type(terminal.duration_ns) is int and terminal.duration_ns >= 0
        attempts.add(start.invocation_id)
        executions.add(start.execution_id)
    assert len(attempts) == len(executions) == 6
    assert "private" not in repr(recorder.pairs)


async def run_guide(path: Path) -> Any:
    name = "_agnara_telemetry_guide_consumer"
    assert name not in sys.modules
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        async with asyncio.timeout(20):
            demo = await module.demonstrate()
        assert asyncio.all_tasks() == {asyncio.current_task()}, "guide tasks survived"
        return demo
    finally:
        del sys.modules[name]


if __name__ == "__main__":
    validate(asyncio.run(run_guide(Path(sys.argv[1]))))
    print("TELEMETRY_GUIDE_ARTIFACT_OK")
