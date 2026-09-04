import asyncio
from collections.abc import AsyncIterator

import pytest

from agnara import InteractionRequiredError, PolicyDeniedError
from agnara.capability import CapabilityDefinition, CapabilityId, Confirmation
from agnara.core.di import DIContainer, DIRegistry, provider
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    invoke,
    invoke_result,
)
from agnara.policy import (
    ConfirmationEvidence,
    ConfirmationVerdict,
    PolicyFailure,
    PolicyInteractionRequired,
    PolicyResult,
    PolicySuccess,
    Principal,
)


class ConfigurableVerifier:
    def __init__(self, verdict: ConfirmationVerdict) -> None:
        self.verdict = verdict

    async def verify(
        self,
        evidence: ConfirmationEvidence,
        *,
        capability_id,
        invocation,
        principal,
    ) -> ConfirmationVerdict:
        return self.verdict


def required_plan(handler, registry: DIRegistry | None = None) -> ExecutionPlan:
    return ExecutionPlan.compile(
        CapabilityDefinition(
            id=CapabilityId("payments", "refund"),
            handler=handler,
            confirmation=Confirmation.REQUIRED,
        ),
        registry or DIRegistry(),
        confirmation_verifier=ConfigurableVerifier(ConfirmationVerdict.VALID),
    )


def context_for(
    plan: ExecutionPlan,
    registry: DIRegistry | None = None,
    *,
    evidence: ConfirmationEvidence | None = None,
    metadata: dict | None = None,
    deadline: float | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        Invocation(plan.definition.id, {}, metadata or {}, deadline),
        DIContainer(registry or DIRegistry()),
        principal=Principal("user_123"),
        confirmation_evidence=evidence,
    )


def test_direct_invocation_raises_typed_interaction_without_handler_effects() -> None:
    async def run_test() -> None:
        calls = 0

        def refund() -> None:
            nonlocal calls
            calls += 1

        plan = required_plan(refund)

        with pytest.raises(InteractionRequiredError) as captured:
            await invoke(plan, context_for(plan))

        assert captured.value.request.capability_id == plan.definition.id
        assert calls == 0

    asyncio.run(run_test())


def test_canonical_invocation_maps_interaction_request() -> None:
    async def run_test() -> None:
        plan = required_plan(lambda: None)

        assert await invoke_result(plan, context_for(plan)) == Failure(
            FailureCode.INTERACTION_REQUIRED,
            "Confirm this capability invocation before continuing.",
            {
                "kind": "confirmation",
                "title": "Confirmation required",
                "capability_id": "payments.refund",
                "hints": (),
            },
        )

    asyncio.run(run_test())


def test_caller_metadata_cannot_substitute_for_confirmation_evidence() -> None:
    async def run_test() -> None:
        plan = required_plan(lambda: None)
        outcome = await invoke_result(
            plan,
            context_for(plan, metadata={"confirmed": True, "confirmation": "valid"}),
        )

        assert isinstance(outcome, Failure)
        assert outcome.code is FailureCode.INTERACTION_REQUIRED

    asyncio.run(run_test())


def test_valid_confirmation_allows_handler() -> None:
    async def run_test() -> None:
        plan = required_plan(lambda: "refunded")

        assert (
            await invoke(
                plan,
                context_for(plan, evidence=ConfirmationEvidence("approval-reference")),
            )
            == "refunded"
        )

    asyncio.run(run_test())


def test_invalid_confirmation_is_forbidden_and_not_an_interaction_or_effect() -> None:
    async def run_test() -> None:
        calls = 0

        def refund() -> None:
            nonlocal calls
            calls += 1

        definition = CapabilityDefinition(
            id=CapabilityId("payments", "refund"),
            handler=refund,
            confirmation=Confirmation.REQUIRED,
        )
        plan = ExecutionPlan.compile(
            definition,
            DIRegistry(),
            confirmation_verifier=ConfigurableVerifier(ConfirmationVerdict.INVALID),
        )
        context = context_for(plan, evidence=ConfirmationEvidence("forged-secret"))

        with pytest.raises(PolicyDeniedError, match="evidence was rejected"):
            await invoke(plan, context)
        assert await invoke_result(plan, context) == Failure(
            FailureCode.FORBIDDEN,
            "confirmation evidence was rejected",
        )
        assert calls == 0

    asyncio.run(run_test())


def test_policy_denial_stops_later_policies_and_dependency_construction() -> None:
    async def run_test() -> None:
        events: list[str] = []

        class Resource:
            pass

        @provider()
        async def provide_resource() -> AsyncIterator[Resource]:
            events.append("dependency")
            yield Resource()

        class Deny:
            async def evaluate(self, context: ExecutionContext) -> PolicyResult:
                events.append("deny")
                return PolicyFailure("not allowed")

        class MustNotRun:
            async def evaluate(self, context: ExecutionContext) -> PolicyResult:
                events.append("later-policy")
                return PolicySuccess()

        registry = DIRegistry()
        registry.bind(Resource, provide_resource)

        def refund(resource: Resource) -> None:
            events.append("handler")

        definition = CapabilityDefinition(
            id=CapabilityId("payments", "refund"),
            handler=refund,
            policies=(Deny(), MustNotRun()),
        )
        plan = ExecutionPlan.compile(definition, registry)

        assert await invoke_result(plan, context_for(plan, registry)) == Failure(
            FailureCode.FORBIDDEN,
            "not allowed",
        )
        assert events == ["deny"]

    asyncio.run(run_test())


def test_unexpected_verifier_exception_is_redacted_at_canonical_boundary() -> None:
    class BrokenVerifier:
        async def verify(self, *args, **kwargs):
            raise RuntimeError("approval database password is secret")

    async def run_test() -> None:
        calls = 0

        def refund() -> None:
            nonlocal calls
            calls += 1

        definition = CapabilityDefinition(
            id=CapabilityId("payments", "refund"),
            handler=refund,
            confirmation=Confirmation.REQUIRED,
        )
        plan = ExecutionPlan.compile(
            definition,
            DIRegistry(),
            confirmation_verifier=BrokenVerifier(),
        )
        outcome = await invoke_result(
            plan,
            context_for(plan, evidence=ConfirmationEvidence("opaque-secret")),
        )

        assert outcome == Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")
        assert isinstance(outcome, Failure)
        assert "secret" not in outcome.message
        assert calls == 0

    asyncio.run(run_test())


def test_deadline_cancels_verifier_and_maps_timeout_without_handler_effects() -> None:
    class WaitingVerifier:
        async def verify(self, *args, **kwargs):
            await asyncio.Event().wait()

    async def run_test() -> None:
        calls = 0

        def refund() -> None:
            nonlocal calls
            calls += 1

        definition = CapabilityDefinition(
            id=CapabilityId("payments", "refund"),
            handler=refund,
            confirmation=Confirmation.REQUIRED,
        )
        plan = ExecutionPlan.compile(
            definition,
            DIRegistry(),
            confirmation_verifier=WaitingVerifier(),
        )
        outcome = await invoke_result(
            plan,
            context_for(
                plan,
                evidence=ConfirmationEvidence("opaque"),
                deadline=asyncio.get_running_loop().time(),
            ),
        )

        assert outcome == Failure(FailureCode.TIMEOUT, "invocation deadline exceeded")
        assert calls == 0

    asyncio.run(run_test())


def test_external_cancellation_propagates_while_verifier_runs() -> None:
    class WaitingVerifier:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = False

        async def verify(self, *args, **kwargs):
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True

    async def run_test() -> None:
        verifier = WaitingVerifier()
        definition = CapabilityDefinition(
            id=CapabilityId("payments", "refund"),
            handler=lambda: None,
            confirmation=Confirmation.REQUIRED,
        )
        plan = ExecutionPlan.compile(
            definition,
            DIRegistry(),
            confirmation_verifier=verifier,
        )
        task = asyncio.create_task(
            invoke_result(
                plan,
                context_for(plan, evidence=ConfirmationEvidence("opaque")),
            )
        )
        await verifier.started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert verifier.cancelled

    asyncio.run(run_test())


def test_explicit_policy_can_request_interaction_without_required_metadata() -> None:
    class ConditionalPolicy:
        async def evaluate(self, context: ExecutionContext) -> PolicyResult:
            from agnara.policy import InteractionKind, InteractionRequest

            return PolicyInteractionRequired(
                InteractionRequest(
                    InteractionKind.CONFIRMATION,
                    "Review refund",
                    "Review this refund before continuing.",
                    context.invocation.capability_id,
                    {"risk": "high"},
                )
            )

    async def run_test() -> None:
        definition = CapabilityDefinition(
            id=CapabilityId("payments", "refund"),
            handler=lambda: None,
            confirmation=Confirmation.POLICY,
            policies=(ConditionalPolicy(),),
        )
        plan = ExecutionPlan.compile(definition, DIRegistry())

        assert await invoke_result(plan, context_for(plan)) == Failure(
            FailureCode.INTERACTION_REQUIRED,
            "Review this refund before continuing.",
            {
                "kind": "confirmation",
                "title": "Review refund",
                "capability_id": "payments.refund",
                "hints": (("risk", "high"),),
            },
        )

    asyncio.run(run_test())
