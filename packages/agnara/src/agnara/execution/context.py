import asyncio
from typing import Any

from agnara.core.di.resolver import DIContainer
from agnara.execution.invocation import Invocation
from agnara.policy.confirmation import ConfirmationEvidence
from agnara.policy.principal import AnonymousPrincipal, Principal

__all__ = ["ExecutionContext"]


class ExecutionContext:
    """The active runtime environment for a single capability execution.

    Holds the transport-neutral context required to evaluate policies, resolve
    dependencies, and execute a compiled plan.
    """

    def __init__(
        self,
        invocation: Invocation,
        di_container: DIContainer,
        tracking_id: str | None = None,
        principal: Principal | None = None,
        confirmation_evidence: ConfirmationEvidence | None = None,
    ) -> None:
        self.invocation = invocation
        self.di_container = di_container
        self.tracking_id = tracking_id
        self.principal = principal or AnonymousPrincipal()
        if confirmation_evidence is not None and not isinstance(
            confirmation_evidence, ConfirmationEvidence
        ):
            raise TypeError("confirmation_evidence must be ConfirmationEvidence or None")
        self.confirmation_evidence = confirmation_evidence
        # State that policies or interceptors might attach during this execution.
        # This is strictly bound to a single capability execution.
        self.state: dict[str, Any] = {}

    @property
    def deadline(self) -> float | None:
        """The invocation's absolute monotonic deadline, when one exists."""
        return self.invocation.deadline

    def remaining_time(self, now: float | None = None) -> float | None:
        """Seconds remaining, clamped to zero, or ``None`` without a deadline."""
        if self.deadline is None:
            return None
        current = asyncio.get_running_loop().time() if now is None else now
        return max(0.0, self.deadline - current)
