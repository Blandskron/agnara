import asyncio
from dataclasses import FrozenInstanceError

import pytest

from agnara.capability import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import ExecutionContext, Invocation
from agnara.policy import (
    ConfirmationEvidence,
    ConfirmationVerdict,
    ConfirmationVerifier,
    InteractionKind,
    PolicyFailure,
    PolicyInteractionRequired,
    PolicySuccess,
    Principal,
)
from agnara.policy.confirmation import ConfirmationPolicy


class RecordingVerifier:
    def __init__(self, verdict: ConfirmationVerdict) -> None:
        self.verdict = verdict
        self.calls: list[tuple[object, ...]] = []

    async def verify(
        self,
        evidence: ConfirmationEvidence,
        *,
        capability_id: CapabilityId,
        invocation: Invocation,
        principal: Principal,
    ) -> ConfirmationVerdict:
        self.calls.append((evidence, capability_id, invocation, principal))
        return self.verdict


def context_for(
    capability_id: CapabilityId,
    evidence: ConfirmationEvidence | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        Invocation(capability_id, {"amount": 1250}, {}),
        DIContainer(DIRegistry()),
        principal=Principal("user_123"),
        confirmation_evidence=evidence,
    )


def test_confirmation_evidence_is_opaque_frozen_and_slotted() -> None:
    evidence = ConfirmationEvidence("secret-approval-reference")

    assert "secret-approval-reference" not in repr(evidence)
    assert not hasattr(evidence, "__dict__")
    with pytest.raises(FrozenInstanceError):
        evidence.value = "replacement"


def test_confirmation_policy_satisfies_verifier_protocol() -> None:
    assert isinstance(RecordingVerifier(ConfirmationVerdict.VALID), ConfirmationVerifier)


def test_missing_evidence_requests_caller_safe_interaction_without_verifying() -> None:
    async def run_test() -> None:
        capability_id = CapabilityId("payments", "refund")
        verifier = RecordingVerifier(ConfirmationVerdict.VALID)
        result = await ConfirmationPolicy(capability_id, verifier).evaluate(
            context_for(capability_id)
        )

        assert isinstance(result, PolicyInteractionRequired)
        assert result.request.kind is InteractionKind.CONFIRMATION
        assert result.request.capability_id == capability_id
        assert result.request.title == "Confirmation required"
        assert verifier.calls == []

    asyncio.run(run_test())


def test_valid_evidence_passes_exact_binding_inputs_to_verifier() -> None:
    async def run_test() -> None:
        capability_id = CapabilityId("payments", "refund")
        evidence = ConfirmationEvidence(object())
        verifier = RecordingVerifier(ConfirmationVerdict.VALID)
        context = context_for(capability_id, evidence)

        assert (
            await ConfirmationPolicy(capability_id, verifier).evaluate(context) == PolicySuccess()
        )
        assert verifier.calls == [(evidence, capability_id, context.invocation, context.principal)]

    asyncio.run(run_test())


def test_invalid_evidence_is_denied_instead_of_requesting_another_interaction() -> None:
    async def run_test() -> None:
        capability_id = CapabilityId("payments", "refund")
        result = await ConfirmationPolicy(
            capability_id,
            RecordingVerifier(ConfirmationVerdict.INVALID),
        ).evaluate(context_for(capability_id, ConfirmationEvidence("invalid")))

        assert result == PolicyFailure("confirmation evidence was rejected")

    asyncio.run(run_test())


def test_unknown_verifier_result_fails_closed() -> None:
    class BrokenVerifier:
        async def verify(self, *args, **kwargs):
            return True

    async def run_test() -> None:
        capability_id = CapabilityId("payments", "refund")
        policy = ConfirmationPolicy(capability_id, BrokenVerifier())

        with pytest.raises(TypeError, match="invalid verdict"):
            await policy.evaluate(context_for(capability_id, ConfirmationEvidence("evidence")))

    asyncio.run(run_test())
