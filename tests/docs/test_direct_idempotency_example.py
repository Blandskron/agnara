"""The public direct-idempotency example keeps authority and effects separate."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from examples.direct_idempotency import demonstrate

from agnara.execution import CapabilityRuntime, Failure, FailureCode, Success


def test_direct_idempotency_example_reuses_only_authorized_matching_success() -> None:
    outcomes, effects = asyncio.run(demonstrate())

    first = outcomes["first"]
    duplicate = outcomes["duplicate"]
    other_principal = outcomes["other_principal"]
    assert isinstance(first, Success)
    assert isinstance(duplicate, Success)
    assert isinstance(other_principal, Success)
    assert first.value == duplicate.value == "receipt-1"
    assert first.execution_id == duplicate.execution_id
    assert other_principal.value == "receipt-2"
    assert other_principal.execution_id != first.execution_id
    changed = outcomes["changed_input"]
    denied = outcomes["permission_lost"]
    assert isinstance(changed, Failure) and changed.code is FailureCode.CONFLICT
    assert isinstance(denied, Failure) and denied.code is FailureCode.FORBIDDEN
    assert effects == [("A-1", 2500), ("A-1", 2500)]


def test_direct_idempotency_example_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "direct_idempotency.py"
    completed = subprocess.run(
        [sys.executable, str(example)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "first: receipt-1",
        "duplicate: receipt-1",
        "changed_input: conflict",
        "permission_lost: forbidden",
        "other_principal: receipt-2",
        "effects: [('A-1', 2500), ('A-1', 2500)]",
        "concurrent_first: receipt-1",
        "concurrent_contender: conflict",
        "concurrent_permission_lost: forbidden",
        "concurrent_duplicate: receipt-1",
        "concurrent_effects: [('A-1', 2500)]",
    ]


def test_concurrent_contender_refuses_without_repeating_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[CapabilityRuntime] = []
    original_close = CapabilityRuntime.aclose

    async def record_close(self: CapabilityRuntime) -> None:
        await original_close(self)
        closed.append(self)

    monkeypatch.setattr(CapabilityRuntime, "aclose", record_close)

    async def run() -> None:
        before = asyncio.all_tasks()
        results, effects = await demonstrate(concurrent=True)
        assert results["first"] == results["duplicate"] == Success("receipt-1")
        assert results["first"].execution_id == results["duplicate"].execution_id
        assert results["contender"] == Failure(
            FailureCode.CONFLICT, "idempotency request is already in progress"
        )
        assert results["contender"].execution_id != results["first"].execution_id
        assert results["permission_lost"] == Failure(
            FailureCode.FORBIDDEN, "required scopes not granted"
        )
        assert effects == [("A-1", 2500)]
        assert len(closed) == 1
        assert asyncio.all_tasks() == before

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["error", "cancellation"])
def test_concurrent_owner_exit_joins_holder_and_closes_runtime(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    original_invoke = CapabilityRuntime.invoke_result
    original_close = CapabilityRuntime.aclose
    closed: list[CapabilityRuntime] = []
    calls = 0

    async def interrupt_contender(self, context):
        nonlocal calls
        calls += 1
        if calls == 2:
            # The first call is already blocked in its handler when the
            # example enters this contender, so owner exit must join it.
            if failure == "cancellation":
                raise asyncio.CancelledError
            raise RuntimeError("demo owner failed")
        return await original_invoke(self, context)

    async def record_close(self: CapabilityRuntime) -> None:
        await original_close(self)
        closed.append(self)

    monkeypatch.setattr(CapabilityRuntime, "invoke_result", interrupt_contender)
    monkeypatch.setattr(CapabilityRuntime, "aclose", record_close)

    async def run() -> None:
        before = asyncio.all_tasks()
        if failure == "cancellation":
            with pytest.raises(asyncio.CancelledError):
                await demonstrate(concurrent=True)
        else:
            with pytest.raises(ExceptionGroup, match="TaskGroup") as caught:
                await demonstrate(concurrent=True)
            assert len(caught.value.exceptions) == 1
            assert str(caught.value.exceptions[0]) == "demo owner failed"
        assert calls == 2
        assert len(closed) == 1
        assert asyncio.all_tasks() == before

    asyncio.run(run())
