"""Negative proofs for the installed schema-contracts guide consumer."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from agnara.execution import Failure, FailureCode
from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.schema_guide import run_guide, validate


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "schema_contracts.py"))


def clone(demo):
    # Failure owns immutable mapping proxies, so share those values and replace
    # the whole failure in mutations. Copy mutable receipts/inputs with aliases
    # preserved, so identity tests still exercise the real guide object graph.
    return deepcopy(
        demo, {id(value): value for value in demo.results.values() if isinstance(value, Failure)}
    )


def test_actual_guide_types_outcomes_and_schemas_pass(demonstrated) -> None:
    validate(demonstrated)


@pytest.mark.parametrize(
    "case", ["mapping", "bad_quantity", "bool_quantity", "extra_field", "bad_currency"]
)
def test_wrong_nested_error_paths_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    changed.results[case] = replace(changed.results[case], details={"path": ("wrong",)})
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["denied", "mapping", "bad_output"])
def test_wrong_failure_codes_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    code = FailureCode.FORBIDDEN if case == "bad_output" else FailureCode.INTERNAL_FAILURE
    changed.results[case] = replace(changed.results[case], code=code)
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["mapping", "bad_output"])
def test_private_diagnostics_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    changed.results[case] = replace(changed.results[case], message="private producer value")
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize(
    "schema,field,value",
    [
        ("input", "additionalProperties", True),
        ("input", "additionalProperties", 0),
        ("input", "required", []),
        ("output", "additionalProperties", True),
        ("output", "required", ["total_cents"]),
        ("annotation_only", "type", "integer"),
    ],
)
def test_weakened_or_invented_schemas_are_rejected(demonstrated, schema, field, value) -> None:
    changed = clone(demonstrated)
    changed.schemas[schema][field] = value
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["direct", "json", "json_defaults"])
def test_incorrect_output_values_are_rejected(demonstrated, case) -> None:
    changed = clone(demonstrated)
    changed.results[case].value.total_cents = "private producer value"
    with pytest.raises(AssertionError):
        validate(changed)


def test_identity_effects_wire_mutation_and_missing_results_are_rejected(demonstrated) -> None:
    changed = clone(demonstrated)
    changed.handled[1] = changed.direct_order
    with pytest.raises(AssertionError):
        validate(changed)
    changed = clone(demonstrated)
    changed.events.insert(0, "denied.handler")
    with pytest.raises(AssertionError):
        validate(changed)
    changed = clone(demonstrated)
    changed.wire_order["currency"] = "USD"
    with pytest.raises(AssertionError):
        validate(changed)
    changed = clone(demonstrated)
    del changed.results["json_defaults"]
    with pytest.raises(AssertionError):
        validate(changed)
    changed = clone(demonstrated)
    changed.results["json"].value.currency = "CLP"
    with pytest.raises(AssertionError):
        validate(changed)
