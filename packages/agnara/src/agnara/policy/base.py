from __future__ import annotations

from collections.abc import Mapping
from dataclasses import field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.identity import CapabilityId

if TYPE_CHECKING:
    from agnara.execution.context import ExecutionContext

__all__ = [
    "InteractionKind",
    "InteractionRequest",
    "Policy",
    "PolicyFailure",
    "PolicyInteractionRequired",
    "PolicyResult",
    "PolicySuccess",
]


type InteractionHint = bool | int | float | str | tuple[InteractionHint, ...] | None


class InteractionKind(StrEnum):
    """Stable protocol-neutral kinds of caller interaction."""

    CONFIRMATION = "confirmation"


@frozen_slots_dataclass
class InteractionRequest:
    """Caller-safe information describing an interaction needed to proceed."""

    kind: InteractionKind
    title: str
    message: str
    capability_id: CapabilityId
    hints: Mapping[str, InteractionHint] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, InteractionKind):
            raise TypeError(f"kind must be an InteractionKind, got {type(self.kind).__name__}")
        if not isinstance(self.title, str) or not self.title:
            raise TypeError("title must be a non-empty string")
        if not isinstance(self.message, str) or not self.message:
            raise TypeError("message must be a non-empty string")
        if not isinstance(self.capability_id, CapabilityId):
            raise TypeError(
                f"capability_id must be a CapabilityId, got {type(self.capability_id).__name__}"
            )
        if not isinstance(self.hints, Mapping):
            raise TypeError("hints must be a mapping")

        copied: dict[str, InteractionHint] = {}
        for key, value in self.hints.items():
            if not isinstance(key, str):
                raise TypeError("interaction hint keys must be strings")
            if not _is_interaction_hint(value):
                raise TypeError(
                    "interaction hint values must be immutable scalars or nested tuples"
                )
            copied[key] = value
        object.__setattr__(self, "hints", MappingProxyType(copied))


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


@frozen_slots_dataclass
class PolicyInteractionRequired:
    """Indicates that execution must stop until the caller completes an interaction."""

    request: InteractionRequest

    def __post_init__(self) -> None:
        if not isinstance(self.request, InteractionRequest):
            raise TypeError(
                f"request must be an InteractionRequest, got {type(self.request).__name__}"
            )


type PolicyResult = PolicySuccess | PolicyFailure | PolicyInteractionRequired


@runtime_checkable
class Policy(Protocol):
    """Protocol for security and execution policies.

    Policies are independently testable rules evaluated against the capability and context.
    They must be transport-neutral and return a PolicyResult instead of raising exceptions.
    """

    async def evaluate(self, context: ExecutionContext) -> PolicyResult: ...


def _is_interaction_hint(value: object) -> bool:
    if value is None or isinstance(value, str | bool | int | float):
        return True
    return isinstance(value, tuple) and all(_is_interaction_hint(item) for item in value)
