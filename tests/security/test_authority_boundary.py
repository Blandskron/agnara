"""The boundary between external authentication and Agnara authorization.

Agnara does not authenticate anyone. A composition root -- an adapter, an
embedding host or a direct caller -- verifies a credential and hands the
kernel a :class:`Principal`: an identity string, opaque metadata and the
scopes the verifier granted. Everything here proves the consequences of that
split, and specifically that nothing *inside* an execution can widen it.

These are the threat-model cases from ``docs/THREAT_MODEL.md`` section 7
"confused deputy, over-broad delegated authority" and boundary B5. RFC 0005
delegation is deliberately unimplemented, so there is no subject, no grant
chain and no attenuation to test: the only authority a child ever sees is the
caller's own, re-evaluated against the child's own declared scopes.
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest

from agnara import Agnara, InvocationError
from agnara.capability import (
    CapabilityDefinition,
    CapabilityId,
    CapabilityRegistry,
    Confirmation,
)
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    Success,
)
from agnara.introspection import (
    DiscoveryVisibility,
    ScopeVisible,
    describe_app,
    filter_snapshot,
    snapshot,
)
from agnara.policy import (
    AnonymousPrincipal,
    ConfirmationEvidence,
    ConfirmationVerdict,
    Principal,
)

REPORT = CapabilityId.parse("billing.report")
TRANSFER = CapabilityId.parse("billing.transfer")

#: The scope a caller in these tests legitimately holds.
ANALYST = "reports:run"
#: The scope it must never acquire by going through a privileged parent.
TREASURY = "payments:transfer"


def runtime_for(plans: list[ExecutionPlan], container: DIContainer) -> CapabilityRuntime:
    capabilities = CapabilityRegistry(plan.definition for plan in plans).freeze()
    return CapabilityRuntime(capabilities, plans, container, max_composition_depth=8)


def context(
    capability_id: CapabilityId,
    container: DIContainer,
    principal: Principal | None = None,
    *,
    metadata: dict[str, object] | None = None,
    evidence: ConfirmationEvidence | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        Invocation(capability_id, {}, metadata or {}, None),
        container,
        principal=principal,
        confirmation_evidence=evidence,
    )


class AcceptingVerifier:
    async def verify(self, evidence, *, capability_id, invocation, principal):
        return ConfirmationVerdict.VALID


def test_a_privileged_parent_cannot_lend_its_authority_to_a_child() -> None:
    """The confused deputy: reachable parent, unreachable child.

    The caller is genuinely authorized to run the report. The report is
    genuinely authorized to move money. Neither fact authorizes *this caller*
    to move money, and the child is refused before the transfer handler runs.
    """

    async def run() -> None:
        registry = DIRegistry()
        transfers: list[str] = []
        child_outcome: list[Failure] = []

        def transfer() -> str:
            transfers.append("moved")
            return "moved"

        async def report(invoker: CapabilityInvoker) -> str:
            outcome = await invoker.invoke(TRANSFER, {})
            assert isinstance(outcome, Failure)
            child_outcome.append(outcome)
            return "report-without-transfer"

        plans = [
            ExecutionPlan.compile(
                CapabilityDefinition(id=TRANSFER, handler=transfer, scopes=frozenset({TREASURY})),
                registry,
            ),
            ExecutionPlan.compile(
                CapabilityDefinition(id=REPORT, handler=report, scopes=frozenset({ANALYST})),
                registry,
            ),
        ]
        container = DIContainer(registry)
        runtime = runtime_for(plans, container)
        analyst = Principal("analyst", scopes={ANALYST})

        outcome = await runtime.invoke_result(context(REPORT, container, analyst))

        # The parent still completes: refusing the child is a result, not a crash.
        assert outcome == Success("report-without-transfer")
        assert child_outcome == [Failure(FailureCode.FORBIDDEN, "required scopes not granted")]
        # The privileged effect never happened.
        assert transfers == []
        await runtime.aclose()

    asyncio.run(run())


def test_a_handler_cannot_replace_the_verified_actor_to_escalate_a_child() -> None:
    """Authority is fixed at the composition root, not chosen mid-execution.

    A nested child derives its authority from ``context.principal``. If a
    running capability could reassign that attribute it would become its own
    authorization authority, which is the amplification path B5 exists to
    deny. The attempt fails closed and the child never runs.
    """

    async def run() -> None:
        registry = DIRegistry()
        transfers: list[str] = []

        def transfer() -> str:
            transfers.append("moved")
            return "moved"

        async def report(execution: ExecutionContext, invoker: CapabilityInvoker) -> str:
            execution.principal = Principal("treasury-service", scopes={TREASURY})
            return "escalated"

        plans = [
            ExecutionPlan.compile(
                CapabilityDefinition(id=TRANSFER, handler=transfer, scopes=frozenset({TREASURY})),
                registry,
            ),
            ExecutionPlan.compile(
                CapabilityDefinition(id=REPORT, handler=report, scopes=frozenset({ANALYST})),
                registry,
            ),
        ]
        container = DIContainer(registry)
        runtime = runtime_for(plans, container)

        outcome = await runtime.invoke_result(
            context(REPORT, container, Principal("analyst", scopes={ANALYST}))
        )

        # Redacted rather than reported: the caller learns nothing about why.
        assert outcome == Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")
        assert transfers == []
        await runtime.aclose()

    asyncio.run(run())


def test_the_verified_authority_inputs_are_fixed_for_the_life_of_an_execution() -> None:
    """``principal``, confirmation and idempotency are construction-time facts."""
    container = DIContainer(DIRegistry())
    execution = context(REPORT, container, Principal("analyst", scopes={ANALYST}))

    with pytest.raises(InvocationError, match="principal is fixed"):
        execution.principal = Principal("root", scopes={TREASURY})
    with pytest.raises(InvocationError, match="confirmation_evidence is fixed"):
        execution.confirmation_evidence = ConfirmationEvidence("forged")
    with pytest.raises(InvocationError, match="idempotency is fixed"):
        execution.idempotency = None

    assert execution.principal.identity == "analyst"
    assert execution.principal.scopes == frozenset({ANALYST})
    assert execution.confirmation_evidence is None

    # ``state`` stays deliberately mutable: it carries policy scratch data for
    # one execution and is never consulted as authority.
    execution.state["note"] = "allowed"
    assert execution.state == {"note": "allowed"}


def test_the_kernel_refuses_a_credential_object_offered_as_a_principal() -> None:
    """A token that merely *looks* like a principal is not one.

    This is the "credentials stay outside the kernel" rule with teeth. The
    object below is duck-type compatible with everything scope evaluation
    reads, so without an explicit type boundary it would have authorized the
    transfer while carrying a raw bearer token into handlers and telemetry.
    """

    class VerifiedToken:
        """A plausible stand-in: claims, scopes and the credential itself."""

        identity = "treasury-service"
        scopes = frozenset({TREASURY})
        metadata: ClassVar[dict[str, object]] = {}
        raw = "<the bearer token this object still carries>"

    container = DIContainer(DIRegistry())

    with pytest.raises(TypeError, match="principal must be a Principal or None"):
        ExecutionContext(
            Invocation(TRANSFER, {}, {}, None),
            container,
            principal=VerifiedToken(),  # ty: ignore[invalid-argument-type]
        )


def test_forged_principal_metadata_is_never_read_as_authority() -> None:
    """Scopes are the only grant channel; metadata is inert policy input.

    A host that maps claims carelessly may copy a whole claims bag into
    metadata. That must not become authority under any conventional name.
    """

    async def run() -> None:
        registry = DIRegistry()
        transfers: list[str] = []

        def transfer() -> str:
            transfers.append("moved")
            return "moved"

        plan = ExecutionPlan.compile(
            CapabilityDefinition(id=TRANSFER, handler=transfer, scopes=frozenset({TREASURY})),
            registry,
        )
        container = DIContainer(registry)
        runtime = runtime_for([plan], container)
        forged = Principal(
            "attacker",
            metadata={
                "scopes": [TREASURY],
                "scp": TREASURY,
                "roles": ["admin"],
                "permissions": [TREASURY],
                "is_admin": True,
            },
            scopes=(),
        )

        outcome = await runtime.invoke_result(context(TRANSFER, container, forged))

        assert outcome == Failure(FailureCode.FORBIDDEN, "required scopes not granted")
        assert transfers == []
        await runtime.aclose()

    asyncio.run(run())


def test_an_actor_cannot_assert_a_subject_through_invocation_metadata() -> None:
    """There is no on-behalf-of channel, so nothing can smuggle one in.

    RFC 0005 is Draft: delegation is unimplemented on purpose. The failure
    mode to guard against is not a broken delegation check but a *fabricated*
    one -- metadata that a future reader might mistake for verified authority.
    """

    async def run() -> None:
        registry = DIRegistry()
        transfers: list[str] = []
        seen: list[ExecutionContext] = []

        def transfer(execution: ExecutionContext) -> str:
            seen.append(execution)
            transfers.append("moved")
            return "moved"

        plan = ExecutionPlan.compile(
            CapabilityDefinition(id=TRANSFER, handler=transfer, scopes=frozenset({TREASURY})),
            registry,
        )
        container = DIContainer(registry)
        runtime = runtime_for([plan], container)

        outcome = await runtime.invoke_result(
            context(
                TRANSFER,
                container,
                Principal("agent", scopes={ANALYST}),
                metadata={
                    "subject": "treasurer",
                    "on_behalf_of": "treasurer",
                    "act_as": "treasurer",
                    "delegation": {"scopes": [TREASURY]},
                },
            )
        )

        assert outcome == Failure(FailureCode.FORBIDDEN, "required scopes not granted")
        assert transfers == []
        assert seen == []
        # The kernel exposes no subject or delegation surface to read at all.
        execution = context(TRANSFER, container, Principal("agent", scopes={ANALYST}))
        assert not hasattr(execution, "subject")
        assert not hasattr(execution, "delegation")
        await runtime.aclose()

    asyncio.run(run())


def test_a_cached_discovery_snapshot_never_authorizes_a_later_invocation() -> None:
    """Seeing a capability is not being allowed to call it (ADR 0008).

    Discovery is filtered per viewer, so a snapshot is a *disclosure*
    decision made for one principal at one moment. Serving a cached copy to
    someone else leaks descriptions -- it must never leak authority.
    """

    async def run() -> None:
        registry = DIRegistry()
        application = Agnara("billing")
        transfers: list[str] = []

        @application.capability(scopes=frozenset({TREASURY}))
        def transfer() -> str:
            transfers.append("moved")
            return "moved"

        plans = [
            ExecutionPlan.compile(application.capabilities[key], registry)
            for key in application.capabilities
        ]
        assert [plan.definition.id for plan in plans] == [TRANSFER]
        container = DIContainer(registry)
        runtime = runtime_for(plans, container)

        treasurer = Principal("treasurer", scopes={TREASURY})
        analyst = Principal("analyst", scopes={ANALYST})
        visibility = DiscoveryVisibility.agent_safe(ScopeVisible())
        document = snapshot(
            [describe_app(application, plans, dependencies=registry)], project="billing"
        )

        # The privileged viewer legitimately discovers the capability, and the
        # unprivileged one does not.
        privileged = filter_snapshot(document, visibility, treasurer)
        unprivileged = filter_snapshot(document, visibility, analyst)
        assert [c.id for app in privileged.applications for c in app.capabilities] == [
            str(TRANSFER)
        ]
        assert unprivileged.applications == ()

        # Replaying the privileged snapshot does not carry the privilege with
        # it: authorization is re-decided from the invoking principal.
        assert privileged.filtered is True
        outcome = await runtime.invoke_result(context(TRANSFER, container, analyst))
        assert outcome == Failure(FailureCode.FORBIDDEN, "required scopes not granted")
        assert transfers == []

        # And discovery is not a gate either: the holder of the scope may call
        # the capability whether or not any snapshot was ever produced.
        assert await runtime.invoke_result(context(TRANSFER, container, treasurer)) == Success(
            "moved"
        )
        assert transfers == ["moved"]
        await runtime.aclose()

    asyncio.run(run())


def test_a_confirmation_verifier_that_fails_leaks_nothing_and_denies() -> None:
    """An unavailable authority is a denial, not an allowance or a disclosure."""

    async def run() -> None:
        registry = DIRegistry()
        transfers: list[str] = []
        secret = "bearer-SECRET-a1b2c3"

        class BrokenVerifier:
            async def verify(self, evidence, *, capability_id, invocation, principal):
                raise RuntimeError(f"confirmation backend unreachable: token={secret}")

        def transfer() -> str:
            transfers.append("moved")
            return "moved"

        plan = ExecutionPlan.compile(
            CapabilityDefinition(id=TRANSFER, handler=transfer, confirmation=Confirmation.REQUIRED),
            registry,
            confirmation_verifier=BrokenVerifier(),
        )
        container = DIContainer(registry)
        runtime = runtime_for([plan], container)

        outcome = await runtime.invoke_result(
            context(
                TRANSFER,
                container,
                Principal("analyst", scopes={ANALYST}),
                evidence=ConfirmationEvidence(secret),
            )
        )

        assert outcome == Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")
        assert secret not in repr(outcome)
        assert transfers == []
        await runtime.aclose()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("verdict", "label"),
    [("valid", "a truthy look-alike string"), (True, "a bare boolean"), (None, "nothing at all")],
)
def test_an_ambiguous_confirmation_verdict_is_not_an_approval(verdict: object, label: str) -> None:
    """Only ``ConfirmationVerdict.VALID`` approves. Everything else denies."""

    async def run() -> None:
        registry = DIRegistry()
        transfers: list[str] = []

        class AmbiguousVerifier:
            async def verify(self, evidence, *, capability_id, invocation, principal):
                return verdict

        def transfer() -> str:
            transfers.append("moved")
            return "moved"

        plan = ExecutionPlan.compile(
            CapabilityDefinition(id=TRANSFER, handler=transfer, confirmation=Confirmation.REQUIRED),
            registry,
            confirmation_verifier=AmbiguousVerifier(),
        )
        container = DIContainer(registry)
        runtime = runtime_for([plan], container)

        outcome = await runtime.invoke_result(
            context(
                TRANSFER,
                container,
                Principal("analyst", scopes={ANALYST}),
                evidence=ConfirmationEvidence("evidence"),
            )
        )

        assert outcome == Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed"), (
            label
        )
        assert transfers == []
        await runtime.aclose()

    asyncio.run(run())


def test_missing_confirmation_evidence_asks_instead_of_assuming() -> None:
    """Absent verifier context is an interaction request, never a pass."""

    async def run() -> None:
        registry = DIRegistry()
        transfers: list[str] = []

        def transfer() -> str:
            transfers.append("moved")
            return "moved"

        plan = ExecutionPlan.compile(
            CapabilityDefinition(id=TRANSFER, handler=transfer, confirmation=Confirmation.REQUIRED),
            registry,
            confirmation_verifier=AcceptingVerifier(),
        )
        container = DIContainer(registry)
        runtime = runtime_for([plan], container)

        outcome = await runtime.invoke_result(
            context(TRANSFER, container, Principal("analyst", scopes={ANALYST}))
        )

        assert isinstance(outcome, Failure)
        assert outcome.code is FailureCode.INTERACTION_REQUIRED
        assert transfers == []
        await runtime.aclose()

    asyncio.run(run())


def test_interleaved_executions_never_exchange_their_principals() -> None:
    """Two callers in flight at once stay two callers.

    The handlers are held at a barrier so both executions -- and both nested
    children -- are live simultaneously. Any shared or ambient identity slot
    would show up here as one caller acting with the other's authority.
    """

    async def run() -> None:
        registry = DIRegistry()
        both_started = asyncio.Event()
        arrived = 0
        observed: dict[str, str] = {}
        child_actors: dict[str, str] = {}

        def child_view(execution: ExecutionContext) -> str:
            child_actors[execution.principal.identity] = execution.principal.identity
            return execution.principal.identity

        async def parent(execution: ExecutionContext, invoker: CapabilityInvoker) -> str:
            nonlocal arrived
            caller = execution.principal.identity
            arrived += 1
            if arrived == 2:
                both_started.set()
            await both_started.wait()
            outcome = await invoker.invoke(TRANSFER, {})
            assert isinstance(outcome, Success)
            observed[caller] = execution.principal.identity
            return outcome.value

        plans = [
            ExecutionPlan.compile(
                CapabilityDefinition(id=TRANSFER, handler=child_view, scopes=frozenset({ANALYST})),
                registry,
            ),
            ExecutionPlan.compile(
                CapabilityDefinition(id=REPORT, handler=parent, scopes=frozenset({ANALYST})),
                registry,
            ),
        ]
        container = DIContainer(registry)
        runtime = runtime_for(plans, container)

        first = Principal("analyst-one", scopes={ANALYST})
        second = Principal("analyst-two", scopes={ANALYST})
        results = await asyncio.gather(
            runtime.invoke_result(context(REPORT, container, first)),
            runtime.invoke_result(context(REPORT, container, second)),
        )

        # Each parent saw its own caller, and each child inherited that caller.
        assert results == [Success("analyst-one"), Success("analyst-two")]
        assert observed == {"analyst-one": "analyst-one", "analyst-two": "analyst-two"}
        assert child_actors == {"analyst-one": "analyst-one", "analyst-two": "analyst-two"}
        await runtime.aclose()

    asyncio.run(run())


def test_an_anonymous_caller_is_a_real_identity_with_no_grants() -> None:
    """Absent authentication resolves to anonymous and fails closed on scopes."""

    async def run() -> None:
        registry = DIRegistry()
        transfers: list[str] = []
        unscoped_ran: list[str] = []

        def transfer() -> str:
            transfers.append("moved")
            return "moved"

        def report() -> str:
            unscoped_ran.append("ran")
            return "ran"

        plans = [
            ExecutionPlan.compile(
                CapabilityDefinition(id=TRANSFER, handler=transfer, scopes=frozenset({TREASURY})),
                registry,
            ),
            ExecutionPlan.compile(CapabilityDefinition(id=REPORT, handler=report), registry),
        ]
        container = DIContainer(registry)
        runtime = runtime_for(plans, container)

        anonymous = context(TRANSFER, container, None)
        assert isinstance(anonymous.principal, AnonymousPrincipal)
        assert anonymous.principal.scopes == frozenset()

        assert await runtime.invoke_result(anonymous) == Failure(
            FailureCode.FORBIDDEN, "required scopes not granted"
        )
        assert transfers == []

        # A capability that declares no scope is not secret: it declares no
        # requirement, and inventing one here would be guessing.
        assert await runtime.invoke_result(context(REPORT, container, None)) == Success("ran")
        assert unscoped_ran == ["ran"]
        await runtime.aclose()

    asyncio.run(run())
