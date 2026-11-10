"""Negative proofs for the installed direct-idempotency guide consumer."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from agnara.execution import Failure, FailureCode, Success
from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.direct_idempotency_guide import run_guide, validate, validate_concurrent

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


@pytest.fixture(scope="module")
def concurrent_demo():
    return asyncio.run(
        run_guide(WORKSPACE_ROOT / "examples" / "direct_idempotency.py", concurrent=True)
    )


def test_actual_concurrent_guide_passes(concurrent_demo) -> None:
    validate_concurrent(concurrent_demo)


@pytest.mark.parametrize(
    "case",
    [
        "missing_contender",
        "extra_result",
        "contender_succeeded",
        "wrong_conflict",
        "diagnostic_leak",
        "holder_identity_leak",
        "duplicate_identity_changed",
        "missing_identity",
        "permission_bypassed",
        "changed_receipt",
        "extra_effect",
        "missing_effect",
        "changed_effect",
    ],
)
def test_concurrent_consumer_rejects_broken_contract(concurrent_demo, case) -> None:
    results, effects = clone(concurrent_demo)
    if case == "missing_contender":
        del results["contender"]
    elif case == "extra_result":
        results["extra"] = results["first"]
    elif case == "contender_succeeded":
        results["contender"] = Success("receipt-2")
    elif case == "wrong_conflict":
        results["contender"] = replace(results["contender"], message="wrong conflict")
    elif case == "diagnostic_leak":
        results["contender"] = replace(results["contender"], details={"key": "private"})
    elif case == "holder_identity_leak":
        results["contender"] = replace(
            results["contender"], execution_id=results["first"].execution_id
        )
    elif case == "duplicate_identity_changed":
        results["duplicate"] = replace(results["duplicate"], execution_id="different")
    elif case == "missing_identity":
        results["first"] = replace(results["first"], execution_id=None)
    elif case == "permission_bypassed":
        results["permission_lost"] = results["first"]
    elif case == "changed_receipt":
        results["duplicate"] = replace(results["duplicate"], value="receipt-2")
    elif case == "extra_effect":
        effects.append(("A-1", 2500))
    elif case == "missing_effect":
        effects.clear()
    else:
        effects[0] = ("A-1", 3000)
    with pytest.raises(AssertionError):
        validate_concurrent((results, effects))
