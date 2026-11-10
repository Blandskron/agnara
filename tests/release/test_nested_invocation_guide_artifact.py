"""Negative proofs for the installed nested invocation guide consumer."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from agnara.execution import Failure, FailureCode, Success
from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.nested_invocation_guide import run_guide, validate

CASES = ("authorized", "child_denied", "parent_denied", "no_scopes")


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "nested_invocation.py"))


def clone(demo):
    return {name: (result, list(calls)) for name, (result, calls) in demo.items()}


def test_actual_guide_outcomes_root_identities_and_effects_pass(demonstrated) -> None:
    validate(demonstrated)
    # Validation must not modify the returned outcomes or effect lists.
    validate(demonstrated)


@pytest.mark.parametrize("case", CASES)
def test_missing_outcomes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    del changed[case]
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("mutation", ["extra", "reordered"])
def test_unexpected_or_reordered_outcomes_are_rejected(demonstrated, mutation) -> None:
    changed = clone(demonstrated)
    if mutation == "extra":
        changed["extra"] = changed["authorized"]
    else:
        changed = dict(reversed(changed.items()))
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["authorized", "child_denied"])
@pytest.mark.parametrize("mutation", ["value", "failure", "raw_value"])
def test_altered_success_or_child_fallback_is_rejected(demonstrated, case, mutation) -> None:
    changed = clone(demonstrated)
    result, calls = changed[case]
    if mutation == "value":
        result = replace(result, value="Summary: incorrect product")
    elif mutation == "failure":
        result = Failure(FailureCode.FORBIDDEN, "required scopes not granted")
    else:
        result = result.value
    changed[case] = (result, calls)
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["parent_denied", "no_scopes"])
@pytest.mark.parametrize("mutation", ["code", "message", "details", "success"])
def test_altered_parent_refusals_are_rejected(demonstrated, case, mutation) -> None:
    changed = clone(demonstrated)
    result, calls = changed[case]
    if mutation == "code":
        result = replace(result, code=FailureCode.INTERNAL_FAILURE)
    elif mutation == "message":
        result = replace(result, message="private policy diagnostic")
    elif mutation == "details":
        result = replace(result, details={"private": "policy internals"})
    else:
        result = Success("Summary: A-1: widget", execution_id=result.execution_id)
    changed[case] = (result, calls)
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("mutation", ["missing", "shared"])
def test_missing_or_shared_root_execution_identity_is_rejected(
    demonstrated, case, mutation
) -> None:
    changed = clone(demonstrated)
    result, calls = changed[case]
    other = "child_denied" if case == "authorized" else "authorized"
    identity = None if mutation == "missing" else changed[other][0].execution_id
    changed[case] = (replace(result, execution_id=identity), calls)
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", CASES)
def test_additional_or_unauthorized_handler_effects_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    changed[case][1].append("product")
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["authorized", "child_denied"])
def test_missing_handler_effects_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    changed[case][1].pop()
    with pytest.raises(AssertionError):
        validate(changed)


def test_reordered_parent_child_effects_are_rejected(demonstrated) -> None:
    changed = clone(demonstrated)
    changed["authorized"][1].reverse()
    with pytest.raises(AssertionError):
        validate(changed)


def test_shared_mutable_denial_observations_are_rejected(demonstrated) -> None:
    changed = clone(demonstrated)
    changed["no_scopes"] = (changed["no_scopes"][0], changed["parent_denied"][1])
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("phase", ["load", "call"])
def test_surviving_guide_tasks_are_rejected_and_module_is_removed(
    tmp_path: Path, phase: str
) -> None:
    source = tmp_path / "leaking_guide.py"
    leak = "asyncio.create_task(asyncio.Event().wait())\n"
    source.write_text(
        "import asyncio\n"
        + (leak if phase == "load" else "")
        + "async def demonstrate(principal):\n"
        + ("    " + leak if phase == "call" else "    return None\n"),
        encoding="utf-8",
    )
    # asyncio.run owns final cancellation of this deliberately broken fixture.
    with pytest.raises(AssertionError, match="guide tasks survived"):
        asyncio.run(run_guide(source))
    assert "_agnara_nested_invocation_guide_consumer" not in sys.modules


def test_module_registration_is_removed_when_loading_fails(tmp_path: Path) -> None:
    source = tmp_path / "broken_guide.py"
    source.write_text('raise RuntimeError("fixture load failure")\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="fixture load failure"):
        asyncio.run(run_guide(source))
    assert "_agnara_nested_invocation_guide_consumer" not in sys.modules
