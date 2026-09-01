from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from agnara.execution import CanonicalResult, Failure, FailureCode, Success


def test_success_is_a_frozen_slotted_value_type() -> None:
    outcome: CanonicalResult[int] = Success(42)

    assert outcome.value == 42
    assert not hasattr(outcome, "__dict__")
    with pytest.raises(FrozenInstanceError, match="cannot assign to field 'value'"):
        outcome.value = 43  # type: ignore[misc]


def test_failure_copies_details_into_an_immutable_mapping() -> None:
    source = {"path": ("customer", "email")}
    failure = Failure(FailureCode.INVALID_INPUT, "invalid email", source)
    source["path"] = ("changed",)

    assert failure.details == {"path": ("customer", "email")}
    assert not hasattr(failure, "__dict__")
    with pytest.raises(TypeError):
        failure.details["path"] = ()  # type: ignore[index]
    with pytest.raises(FrozenInstanceError, match="cannot assign to field 'message'"):
        failure.message = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "code",
    [
        FailureCode.INVALID_INPUT,
        FailureCode.UNAUTHENTICATED,
        FailureCode.FORBIDDEN,
        FailureCode.NOT_FOUND,
        FailureCode.CONFLICT,
        FailureCode.RATE_LIMITED,
        FailureCode.INTERACTION_REQUIRED,
        FailureCode.UNAVAILABLE,
        FailureCode.TIMEOUT,
        FailureCode.INTERNAL_FAILURE,
    ],
)
def test_failure_codes_are_stable_protocol_neutral_strings(code: FailureCode) -> None:
    assert str(code) == code.value
    assert code.value.islower()


def test_failure_rejects_mutable_detail_values() -> None:
    mutable_details: Any = {"errors": ["one"]}
    with pytest.raises(TypeError, match="immutable scalars"):
        Failure(FailureCode.INVALID_INPUT, "invalid", mutable_details)
