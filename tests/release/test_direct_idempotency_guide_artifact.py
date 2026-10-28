"""Negative proofs for the installed direct-idempotency guide consumer."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from agnara.execution import Failure, FailureCode
from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.direct_idempotency_guide import run_guide, validate

CASES = ("first", "duplicate", "changed_input", "permission_lost", "other_principal")


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "direct_idempotency.py"))


def clone(demo):
    results, effects = demo
    return dict(results), list(effects)


def test_actual_guide_outcomes_identities_and_effects_pass(demonstrated) -> None:
    validate(demonstrated)


@pytest.mark.parametrize("case", CASES)
def test_missing_outcomes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    del changed[0][case]
    with pytest.raises(AssertionError):
        validate(changed)


def test_unexpected_outcomes_are_rejected(demonstrated) -> None:
    changed = clone(demonstrated)
    changed[0]["extra"] = changed[0]["first"]
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["first", "duplicate", "other_principal"])
@pytest.mark.parametrize("change", ["value", "refusal", "missing_identity"])
def test_altered_successes_are_rejected(demonstrated, case, change) -> None:
    changed = clone(demonstrated)
    result = changed[0][case]
    if change == "value":
        result = replace(result, value="wrong receipt")
    elif change == "refusal":
        result = Failure(FailureCode.INTERNAL_FAILURE, "failed", execution_id=result.execution_id)
    else:
        result = replace(result, execution_id=None)
    changed[0][case] = result
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["changed_input", "permission_lost"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("code", FailureCode.INTERNAL_FAILURE),
        ("message", "private store diagnostic"),
        ("details", {"private": "stored receipt bytes"}),
    ],
)
def test_altered_refusals_and_diagnostics_are_rejected(demonstrated, case, field, value) -> None:
    changed = clone(demonstrated)
    changed[0][case] = replace(changed[0][case], **{field: value})
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["duplicate_changed", "principal_shared", "all_missing"])
def test_invalid_execution_identity_relationships_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    results = changed[0]
    if case == "all_missing":
        for name, result in results.items():
            results[name] = replace(result, execution_id=None)
    else:
        name = "duplicate" if case == "duplicate_changed" else "other_principal"
        identity = (
            "independent-execution"
            if case == "duplicate_changed"
            else results["first"].execution_id
        )
        results[name] = replace(results[name], execution_id=identity)
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["missing", "extra", "amount", "order"])
def test_changed_or_duplicate_effects_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    effects = changed[1]
    if case == "missing":
        effects.pop()
    elif case == "extra":
        effects.append(("A-1", 2500))
    elif case == "amount":
        effects[0] = ("A-1", 3000)
    else:
        effects[0] = ("B-2", 2500)
    with pytest.raises(AssertionError):
        validate(changed)
