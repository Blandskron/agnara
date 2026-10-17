"""Negative proofs for the installed dependency lifecycle guide consumer."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from agnara.execution import Failure, FailureCode, Success
from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.dependencies_guide import run_guide, validate


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "dependencies.py"))


def clone(demo):
    # Preserve resource aliases, sharing only immutable canonical failures.
    return deepcopy(
        demo, {id(value): value for value in demo.results.values() if isinstance(value, Failure)}
    )


def test_actual_guide_outcomes_identity_and_cleanup_pass(demonstrated) -> None:
    validate(demonstrated)


@pytest.mark.parametrize("case", ["denied", "invalid", "failed"])
def test_wrong_codes_and_private_diagnostics_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    code = FailureCode.FORBIDDEN if case == "failed" else FailureCode.INTERNAL_FAILURE
    changed.results[case] = replace(changed.results[case], code=code)
    with pytest.raises(AssertionError):
        validate(changed)
    for field in ("message", "details"):
        changed = clone(demonstrated)
        value = "private fixture diagnostic" if field == "message" else {"private": "diagnostic"}
        changed.results[case] = replace(changed.results[case], **{field: value})
        with pytest.raises(AssertionError):
            validate(changed)


@pytest.mark.parametrize("case", ["first", "second"])
def test_changed_success_is_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    changed.results[case] = Success("wrong")
    with pytest.raises(AssertionError):
        validate(changed)


def test_wrong_path_missing_result_and_unredacted_failure_are_rejected(demonstrated) -> None:
    for case, replacement in (
        ("invalid", replace(demonstrated.results["invalid"], details={"path": ("fail",)})),
        ("failed", replace(demonstrated.results["failed"], message="producer diagnostic")),
        ("failed", replace(demonstrated.results["failed"], details={"debug": "value"})),
    ):
        changed = clone(demonstrated)
        changed.results[case] = replacement
        with pytest.raises(AssertionError):
            validate(changed)
    changed = clone(demonstrated)
    del changed.results["denied"]
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize(
    "case", ["extra_effect", "missing_close", "wrong_order", "early_pool_close"]
)
def test_effect_and_cleanup_trace_changes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    if case == "extra_effect":
        changed.events.insert(0, "handler.enter")
    elif case == "missing_close":
        changed.events.remove("reader.close")
    elif case == "wrong_order":
        changed.events[4:6] = reversed(changed.events[4:6])
    else:
        changed.events.insert(6, changed.events.pop())
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("collection", ["pools", "sessions", "readers", "writers"])
def test_extra_resources_are_rejected(demonstrated, collection) -> None:
    changed = clone(demonstrated)
    resources = getattr(changed, collection)
    resources.append(resources[0])
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("collection", ["pools", "sessions", "readers"])
def test_unclosed_resources_are_rejected(demonstrated, collection) -> None:
    changed = clone(demonstrated)
    getattr(changed, collection)[0].closed = False
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["reused_session", "reader_branch", "writer_branch", "pool"])
def test_broken_resource_identity_is_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    if case == "reused_session":
        changed.sessions[1] = changed.sessions[0]
        changed.readers[1].session = changed.sessions[0]
        changed.writers[1].session = changed.sessions[0]
    elif case == "reader_branch":
        changed.readers[0].session = changed.sessions[1]
    elif case == "writer_branch":
        changed.writers[0].session = changed.sessions[1]
    else:
        changed.sessions[0].pool = deepcopy(changed.pools[0])
    with pytest.raises(AssertionError):
        validate(changed)
