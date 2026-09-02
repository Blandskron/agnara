"""Protocol-neutral confirmation evidence verification."""

from __future__ import annotations

from dataclasses import field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.identity import CapabilityId
from agnara.policy.base import (
    InteractionKind,
    InteractionRequest,
    PolicyFailure,
    PolicyInteractionRequired,
    PolicyResult,
    PolicySuccess,
)

if TYPE_CHECKING:
    from agnara.execution.context import ExecutionContext
    from agnara.execution.invocation import Invocation
    from agnara.policy.principal import Principal

__all__ = [
    "ConfirmationEvidence",
    "ConfirmationPolicy",
    "ConfirmationVerdict",
    "ConfirmationVerifier",
]


@frozen_slots_dataclass
class ConfirmationEvidence:
    """Opaque evidence supplied to a configured confirmation authority.

    Core never interprets or serializes ``value``. Its concrete format and
    authenticity belong to the verifier implementation.
    """

    value: object = field(repr=False)


class ConfirmationVerdict(StrEnum):
    """The only accepted outcomes from a confirmation verifier."""

    VALID = "valid"
    INVALID = "invalid"


@runtime_checkable
class ConfirmationVerifier(Protocol):
    """Application boundary that validates evidence for one exact invocation.

    Implementations own authenticity, canonical input binding, expiry and
    replay protection. All target values are supplied explicitly so evidence
    cannot silently authorize another capability or principal.
    """

    async def verify(
        self,
        evidence: ConfirmationEvidence,
        *,
        capability_id: CapabilityId,
        invocation: Invocation,
        principal: Principal,
    ) -> ConfirmationVerdict: ...


@frozen_slots_dataclass
class ConfirmationPolicy:
    """Require verifier-backed evidence before a capability may execute."""

    capability_id: CapabilityId
    verifier: ConfirmationVerifier
    request: InteractionRequest = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.capability_id, CapabilityId):
            raise TypeError(
                f"capability_id must be a CapabilityId, got {type(self.capability_id).__name__}"
            )
        if not isinstance(self.verifier, ConfirmationVerifier):
            raise TypeError("verifier must implement the ConfirmationVerifier protocol")
        object.__setattr__(
            self,
            "request",
            InteractionRequest(
                kind=InteractionKind.CONFIRMATION,
                title="Confirmation required",
                message="Confirm this capability invocation before continuing.",
                capability_id=self.capability_id,
            ),
        )

    async def evaluate(self, context: ExecutionContext) -> PolicyResult:
        evidence = context.confirmation_evidence
        if evidence is None:
            return PolicyInteractionRequired(self.request)

        verdict = await self.verifier.verify(
            evidence,
            capability_id=self.capability_id,
            invocation=context.invocation,
            principal=context.principal,
        )
        if verdict is ConfirmationVerdict.VALID:
            return PolicySuccess()
        if verdict is ConfirmationVerdict.INVALID:
            return PolicyFailure("confirmation evidence was rejected")
        raise TypeError(
            f"confirmation verifier returned an invalid verdict: {type(verdict).__name__}"
        )
