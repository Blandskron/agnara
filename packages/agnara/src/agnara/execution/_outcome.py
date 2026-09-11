"""One classification of a raised exception into a canonical ``Failure``.

Two boundaries need this answer. ``invoke_result`` gives it for a complete
result, and a stream gives it for a failure that arrives after output has
already reached the consumer (ADR 0084 D6). If each spelled the rules out
itself, the same capability could be redacted on one boundary and not the
other, which is the kind of divergence ADR 0077 exists to prevent.

Nothing here is public. See ``agnara.execution.runtime`` and
``agnara.execution.streaming``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agnara.errors import (
    InteractionRequiredError,
    PolicyDeniedError,
    UnknownCapabilityError,
    ValidationError,
)
from agnara.execution.result import Failure, FailureCode

if TYPE_CHECKING:
    from agnara.capability.identity import CapabilityId

__all__: list[str] = []

#: Where a redacted handler failure is reported. The canonical outcome a
#: caller receives says only that the invocation failed; the exception itself
#: is for the operator, and the log is the one channel that reaches them.
LOGGER = logging.getLogger("agnara.execution")


def classify(error: Exception, capability_id: CapabilityId) -> Failure:
    """Map a raised exception onto the canonical failure it deserves.

    Known runtime errors receive stable semantic categories. Anything else is
    redacted: application exceptions may carry credentials, payload fragments
    or dependency values, so the capability identifier is kept for
    correlation and the exception text and traceback are not.

    ``asyncio.CancelledError`` is never passed here. Cancellation is control
    flow (ADR 0084 D5) and callers re-raise it before reaching this function.
    """
    if isinstance(error, ValidationError):
        return Failure(
            FailureCode.INVALID_INPUT,
            error.message,
            details={"path": error.path},
        )
    if isinstance(error, TimeoutError):
        return Failure(FailureCode.TIMEOUT, "invocation deadline exceeded")
    if isinstance(error, UnknownCapabilityError):
        return Failure(FailureCode.NOT_FOUND, str(error))
    if isinstance(error, PolicyDeniedError):
        return Failure(FailureCode.FORBIDDEN, str(error))
    if isinstance(error, InteractionRequiredError):
        request = error.request
        return Failure(
            FailureCode.INTERACTION_REQUIRED,
            request.message,
            details={
                "kind": request.kind.value,
                "title": request.title,
                "capability_id": str(request.capability_id),
                "hints": tuple(sorted(request.hints.items())),
            },
        )
    LOGGER.error("capability %s failed", capability_id)
    return Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")
