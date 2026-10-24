"""Negative proofs for the installed direct streaming tutorial consumer."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agnara.execution import Failure, FailureCode, StreamTerminal
from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.direct_streaming_guide import CASES, run_guide, validate


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "direct_streaming.py"))


def test_actual_guide_and_cancellation_pass(demonstrated) -> None:
    validate(demonstrated)
    validate(demonstrated)  # Validation leaves observations intact.
    assert "_agnara_direct_streaming_guide_consumer" not in sys.modules


@pytest.mark.parametrize("case", CASES)
def test_missing_case_is_rejected(demonstrated, case) -> None:
    outcomes, events = demonstrated
    changed = dict(outcomes)
    del changed[case]
    with pytest.raises(AssertionError):
        validate((changed, events))


@pytest.mark.parametrize("mutation", ["extra", "reordered"])
def test_extra_or_reordered_cases_are_rejected(demonstrated, mutation) -> None:
    outcomes, events = demonstrated
    changed = dict(outcomes)
    if mutation == "extra":
        changed["extra"] = changed["completed"]
    else:
        changed = dict(reversed(changed.items()))
    with pytest.raises(AssertionError):
        validate((changed, events))


@pytest.mark.parametrize(
    ("case", "field", "value"),
    [
        ("completed", "units", (9, 1)),
        ("completed", "units", (False, True)),
        ("completed", "units", (0.0, 1.0)),
        ("completed", "units", [0, 1]),
        ("completed", "units_emitted", 1),
        ("abandoned", "units_emitted", True),
        ("denied", "units_emitted", False),
        ("completed", "units_emitted", 2.0),
        ("completed", "terminal", "completed"),
        ("abandoned", "terminal", StreamTerminal.COMPLETED),
        ("denied", "terminal", StreamTerminal.ABANDONED),
        ("invalid_input", "refusal", "forbidden"),
        ("denied", "refusal", None),
        ("completed", "refusal", "forbidden"),
        ("late_failure", "terminal", StreamTerminal.COMPLETED),
        ("invalid_output", "units", (0, 1)),
        ("invalid_output", "units_emitted", 2),
        ("first_failure", "failure", None),
        ("late_failure", "failure", Failure(FailureCode.FORBIDDEN, "capability invocation failed")),
        (
            "late_failure",
            "failure",
            Failure(FailureCode.INTERNAL_FAILURE, "demo-private-diagnostic"),
        ),
        (
            "invalid_output",
            "failure",
            Failure(
                FailureCode.INTERNAL_FAILURE,
                "capability invocation failed",
                details={"private": "demo-private-output"},
            ),
        ),
        ("first_failure", "failure", "internal_failure"),
        (
            "completed",
            "failure",
            Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed"),
        ),
        ("denied", "failure", Failure(FailureCode.FORBIDDEN, "required scopes not granted")),
    ],
)
def test_altered_outcomes_and_diagnostics_are_rejected(demonstrated, case, field, value) -> None:
    outcomes, events = demonstrated
    changed = {**outcomes, case: replace(outcomes[case], **{field: value})}
    with pytest.raises(AssertionError):
        validate((changed, events))


@pytest.mark.parametrize(
    ("case", "mutation"),
    [
        (case, mutation)
        for case in CASES
        for mutation in ("missing", "extra", "reordered", "mutable")
        if mutation != "reordered" or case not in ("denied", "invalid_input")
    ],
)
def test_changed_demand_effects_or_cleanup_are_rejected(demonstrated, case, mutation) -> None:
    outcomes, cancelled = demonstrated
    events = outcomes[case].events
    if mutation == "missing":
        events = events[:-1]
    elif mutation == "extra":
        events += ("produce:unexpected",)
    elif mutation == "reordered":
        events = tuple(reversed(events))
    else:
        events = list(events)
    changed = {**outcomes, case: replace(outcomes[case], events=events)}
    with pytest.raises(AssertionError):
        validate((changed, cancelled))


@pytest.mark.parametrize("mutation", ["missing", "extra", "reordered", "mutable"])
def test_changed_cancellation_cleanup_is_rejected(demonstrated, mutation) -> None:
    outcomes, events = demonstrated
    if mutation == "missing":
        events = events[:-1]
    elif mutation == "extra":
        events += ("consume:0",)
    elif mutation == "reordered":
        events = events[:-2] + tuple(reversed(events[-2:]))
    else:
        events = list(events)
    with pytest.raises(AssertionError):
        validate((outcomes, events))


@pytest.mark.parametrize("phase", ["load", "demonstrate", "cancel"])
def test_surviving_tasks_are_rejected_and_module_removed(tmp_path: Path, phase: str) -> None:
    source = tmp_path / "leaking_guide.py"
    leak = "asyncio.create_task(asyncio.Event().wait())\n"
    source.write_text(
        "import asyncio\n"
        + (leak if phase == "load" else "")
        + "async def demonstrate():\n"
        + ("    " + leak if phase == "demonstrate" else "")
        + "    return {}\n"
        + "async def run_case(mode, *, waiting, events):\n"
        + ("    " + leak if phase == "cancel" else "")
        + "    waiting.set()\n"
        + "    await asyncio.Event().wait()\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="guide tasks survived"):
        asyncio.run(run_guide(source))
    assert "_agnara_direct_streaming_guide_consumer" not in sys.modules


def test_swallowed_cancellation_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "swallowed_cancellation.py"
    source.write_text(
        "import asyncio\n"
        "async def demonstrate():\n"
        "    return {}\n"
        "async def run_case(mode, *, waiting, events):\n"
        "    waiting.set()\n"
        "    try:\n"
        "        await asyncio.Event().wait()\n"
        "    except asyncio.CancelledError:\n"
        "        return None\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="caller cancellation did not propagate"):
        asyncio.run(run_guide(source))
    assert "_agnara_direct_streaming_guide_consumer" not in sys.modules


def test_failed_import_removes_module(tmp_path: Path) -> None:
    source = tmp_path / "broken_guide.py"
    source.write_text('raise RuntimeError("fixture load failure")\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="fixture load failure"):
        asyncio.run(run_guide(source))
    assert "_agnara_direct_streaming_guide_consumer" not in sys.modules
