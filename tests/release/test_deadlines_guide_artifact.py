"""Negative proofs for the installed deadline/cancellation guide consumer."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from agnara.execution import Failure, FailureCode, Success
from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.deadlines_guide import run_guide, validate


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "deadlines.py"))


def clone(demo):
    return deepcopy(
        demo, {id(value): value for value in demo[0].values() if isinstance(value, Failure)}
    )


def test_actual_guide_outcomes_and_cleanup_pass(demonstrated) -> None:
    validate(demonstrated)


@pytest.mark.parametrize("case", ["denied", "timeout"])
def test_wrong_failures_and_diagnostics_are_rejected(demonstrated, case) -> None:
    for field, value in (
        ("code", FailureCode.INTERNAL_FAILURE),
        ("message", "private diagnostic"),
        ("message", "unexpected diagnostic"),
        ("details", {"debug": "private diagnostic"}),
        ("details", {"extra": "value"}),
    ):
        changed = clone(demonstrated)
        changed[0][case] = replace(changed[0][case], **{field: value})
        with pytest.raises(AssertionError):
            validate(changed)


@pytest.mark.parametrize(
    "case", ["success", "cancelled_success", "cancelled_failure", "cancelled_text"]
)
def test_changed_success_and_translated_cancellation_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    if case == "success":
        changed[0]["success"] = Success("wrong")
    elif case == "cancelled_success":
        changed[0]["cancelled"] = Success("CancelledError")
    elif case == "cancelled_failure":
        changed[0]["cancelled"] = Failure(FailureCode.TIMEOUT, "invocation deadline exceeded")
    else:
        changed[0]["cancelled"] = "TimeoutError"
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["success", "denied", "timeout", "cancelled"])
def test_missing_outcomes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    del changed[0][case]
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize(
    "case",
    ["extra_scope", "missing_exit", "missing_close", "wrong_order", "early_close", "missing_scope"],
)
def test_effect_and_teardown_changes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    events = changed[1]
    if case == "extra_scope":
        events.extend(["session.open", "handler.enter", "handler.exit", "session.close"])
    elif case == "missing_exit":
        events.remove("handler.exit")
    elif case == "missing_close":
        events.remove("session.close")
    elif case == "wrong_order":
        events[2:4] = reversed(events[2:4])
    elif case == "early_close":
        events.insert(1, events.pop(3))
    else:
        del events[4:8]
    with pytest.raises(AssertionError):
        validate(changed)
