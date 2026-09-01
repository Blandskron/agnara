from typing import Any

from agnara.core.di.resolver import DIContainer
from agnara.execution.invocation import Invocation

__all__ = ["ExecutionContext"]


class ExecutionContext:
    """The active runtime environment for a single capability execution.

    Holds the transport-neutral context required to evaluate policies, resolve
    dependencies, and execute a compiled plan.
    """

    def __init__(
        self, invocation: Invocation, di_container: DIContainer, tracking_id: str | None = None
    ) -> None:
        self.invocation = invocation
        self.di_container = di_container
        self.tracking_id = tracking_id
        # State that policies or interceptors might attach during this execution.
        # This is strictly bound to a single capability execution.
        self.state: dict[str, Any] = {}
