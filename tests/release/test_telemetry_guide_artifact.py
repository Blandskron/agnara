"""Negative proofs for the installed local telemetry guide consumer."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from agnara import CapabilityId
from agnara.execution import Failure, FailureCode, Success
from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.telemetry_guide import run_guide, validate


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "invocation_telemetry.py"))


def clone(demo):
    return deepcopy(
        demo, {id(value): value for value in demo[0].values() if isinstance(value, Failure)}
    )


def test_actual_guide_outcomes_pairs_and_privacy_pass(demonstrated) -> None:
    validate(demonstrated)


@pytest.mark.parametrize("case", ["denied", "invalid", "failed", "timeout"])
def test_changed_codes_and_private_failures_are_rejected(demonstrated, case) -> None:
    for field, value in (
        ("code", FailureCode.FORBIDDEN if case == "failed" else FailureCode.INTERNAL_FAILURE),
        ("message", "private-handler-diagnostic"),
        ("details", {"diagnostic": "private-observer-diagnostic"}),
    ):
        changed = clone(demonstrated)
        changed[0][case] = replace(changed[0][case], **{field: value})
        with pytest.raises(AssertionError):
            validate(changed)


@pytest.mark.parametrize(
    "case", ["success", "cancelled", "path", "redaction", "details", "missing"]
)
def test_changed_results_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    results = changed[0]
    if case == "success":
        results["success"] = Success("wrong")
    elif case == "cancelled":
        results["cancelled"] = Success("CancelledError")
    elif case == "path":
        results["invalid"] = replace(results["invalid"], details={"path": ("wrong",)})
    elif case == "redaction":
        results["failed"] = replace(results["failed"], message="producer diagnostic")
    elif case == "details":
        results["failed"] = replace(results["failed"], details={"debug": "value"})
    else:
        del results["timeout"]
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize(
    "case", ["effect", "starts", "terminals", "pending", "missing", "unpaired"]
)
def test_effects_observer_counts_and_incomplete_pairs_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    _, recorder, faulty, effects = changed
    if case == "effect":
        effects.insert(0, "denied")
    elif case in {"starts", "terminals"}:
        setattr(faulty, case, 5)
    elif case == "pending":
        recorder.pending["leftover"] = recorder.pairs[0][0]
    elif case == "missing":
        recorder.pairs.pop()
    else:
        recorder.pairs[0] = (None, recorder.pairs[0][1])
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize(
    "field,value",
    [
        ("capability_id", CapabilityId.parse("jobs.other")),
        ("tracking_id", "other"),
        ("invocation_id", "unpaired"),
        ("execution_id", "unpaired"),
        ("parent_execution_id", "unexpected-parent"),
        ("outcome", "success"),
        ("units", 0),
        ("duration_ns", -1),
        ("duration_ns", True),
        ("duration_ns", 1.5),
    ],
)
def test_changed_terminal_fields_are_rejected(demonstrated, field, value) -> None:
    changed = clone(demonstrated)
    start, terminal = changed[1].pairs[-1]
    changed[1].pairs[-1] = (start, replace(terminal, **{field: value}))
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("field", ["invocation_id", "execution_id"])
@pytest.mark.parametrize("case", ["empty", "missing", "duplicate", "private"])
def test_matched_but_invalid_identities_are_rejected(demonstrated, field, case) -> None:
    changed = clone(demonstrated)
    pairs = changed[1].pairs
    value = {"empty": "", "missing": None, "private": "private-result"}.get(
        case, getattr(pairs[0][0], field)
    )
    start, terminal = pairs[-1]
    pairs[-1] = (replace(start, **{field: value}), replace(terminal, **{field: value}))
    with pytest.raises(AssertionError):
        validate(changed)
