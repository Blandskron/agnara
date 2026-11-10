"""Validation of declared capability output without transport semantics.

Output is a producer obligation, unlike invocation input.  A caller must not
learn a handler's value or a schema's internal diagnostic when that obligation
is broken, so the public execution boundaries classify a violation as a
redacted internal failure (ADR 0086).
"""

from __future__ import annotations

from typing import Any

from agnara.errors import InvocationError, ValidationError
from agnara.execution.plan import ExecutionPlan
from agnara.execution.result import Failure, Success

__all__: list[str] = []


def validate_output(plan: ExecutionPlan, value: Any) -> Any:
    """Validate one successful output and retain explicit canonical failures.

    A handler may deliberately return ``Failure`` from the complete-result
    boundary; it is already an outcome, not successful output.  A ``Success``
    carries the output to validate. This interpretation belongs to complete
    results; the stream owner validates each actual yielded object as a unit.
    """
    if isinstance(value, Failure):
        return value
    payload = value.value if isinstance(value, Success) else value
    validated = validate_output_unit(plan, payload)
    if isinstance(value, Success):
        return Success(validated)
    return validated


def validate_output_unit(plan: ExecutionPlan, value: Any) -> Any:
    """Validate an actual produced value without canonical envelope semantics."""
    try:
        return plan.output_schema.validate(value)
    except ValidationError as error:
        raise InvocationError(
            f"capability {plan.definition.id} produced a value that does not satisfy "
            "its declared output"
        ) from error
