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
    carries the output to validate.  Streams never use that wrapper: every
    yielded value is a unit and is validated directly by their owner.
    """
    if isinstance(value, Failure):
        return value
    payload = value.value if isinstance(value, Success) else value
    try:
        validated = plan.output_schema.validate(payload)
    except ValidationError as error:
        raise InvocationError(
            f"capability {plan.definition.id} produced a value that does not satisfy "
            "its declared output"
        ) from error
    if isinstance(value, Success):
        return Success(validated)
    return validated
