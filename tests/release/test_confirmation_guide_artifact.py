"""Negative proofs for the installed verifier-backed confirmation guide consumer."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from agnara.execution import FailureCode, Success
from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.confirmation_guide import run_guide, validate

CASES = (
    "missing",
    "metadata_flag",
    "forged",
    "changed_input",
    "other_actor",
    "scope_lost",
    "approved",
    "replay",
    "expired",
)


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "confirmation.py"))


def clone(demo):
    # Canonical results are immutable; replace whole outcomes in mutations.
    results, effects = demo
    return dict(results), list(effects)


def test_actual_guide_outcomes_and_approved_effects_pass(demonstrated) -> None:
    validate(demonstrated)


@pytest.mark.parametrize("case", [case for case in CASES if case != "approved"])
def test_changed_failure_codes_and_diagnostics_are_rejected(demonstrated, case) -> None:
    for field, value in (
        ("code", FailureCode.INTERNAL_FAILURE),
        ("message", "private verifier diagnostic"),
        ("details", {"reference": "unknown-approval"}),
    ):
        changed = clone(demonstrated)
        changed[0][case] = replace(changed[0][case], **{field: value})
        with pytest.raises(AssertionError):
            validate(changed)


@pytest.mark.parametrize("case", ["missing", "metadata_flag"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "other"),
        ("title", "private verifier diagnostic"),
        ("capability_id", "catalog.other"),
        ("hints", ("unknown-approval",)),
        ("extra", "private verifier diagnostic"),
    ],
)
def test_altered_interaction_envelopes_are_rejected(demonstrated, case, field, value) -> None:
    changed = clone(demonstrated)
    outcome = changed[0][case]
    changed[0][case] = replace(outcome, details={**outcome.details, field: value})
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", CASES)
def test_missing_outcomes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    del changed[0][case]
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["value", "refusal"])
def test_incorrect_approved_result_is_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    changed[0]["approved"] = Success("wrong") if case == "value" else changed[0]["replay"]
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize(
    "case", ["extra_archive", "missing_open", "missing_close", "order", "none"]
)
def test_unapproved_effects_and_cleanup_changes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    effects = changed[1]
    if case == "extra_archive":
        effects.insert(1, "archive:A-2")
    elif case == "missing_open":
        effects.remove("resource.open")
    elif case == "missing_close":
        effects.remove("resource.close")
    elif case == "order":
        effects.reverse()
    else:
        effects.clear()
    with pytest.raises(AssertionError):
        validate(changed)
