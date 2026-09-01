from typing import TYPE_CHECKING, Protocol, runtime_checkable

from agnara._frozen import frozen_slots_dataclass

if TYPE_CHECKING:
    from agnara.execution.context import ExecutionContext

__all__ = ["Policy", "PolicyFailure", "PolicyResult", "PolicySuccess"]


@frozen_slots_dataclass
class PolicySuccess:
    """Indicates that the policy evaluation passed."""

    pass


@frozen_slots_dataclass
class PolicyFailure:
    """Indicates that the policy evaluation failed.

    The reason string explains why the policy failed. It should be safe to expose
    to the caller, without leaking internal security details.
    """

    reason: str


type PolicyResult = PolicySuccess | PolicyFailure


@runtime_checkable
class Policy(Protocol):
    """Protocol for security and execution policies.

    Policies are independently testable rules evaluated against the capability and context.
    They must be transport-neutral and return a PolicyResult instead of raising exceptions.
    """

    async def evaluate(self, context: "ExecutionContext") -> PolicyResult: ...
