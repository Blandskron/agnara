import asyncio
import typing
from dataclasses import FrozenInstanceError

import pytest

from agnara.capability import CapabilityId
from agnara.execution.context import ExecutionContext
from agnara.policy.base import (
    InteractionKind,
    InteractionRequest,
    Policy,
    PolicyFailure,
    PolicyInteractionRequired,
    PolicyResult,
    PolicySuccess,
)


class DummyPolicy(Policy):
    async def evaluate(self, context: ExecutionContext) -> PolicyResult:
        if getattr(context, "state", {}).get("fail"):
            return PolicyFailure(reason="configured to fail")
        return PolicySuccess()


def test_policy_protocol():
    async def run_test():
        policy = DummyPolicy()

        class DummyContext:
            state: typing.ClassVar[dict] = {}

        ctx = DummyContext()
        result = await policy.evaluate(typing.cast(ExecutionContext, ctx))
        assert isinstance(result, PolicySuccess)

        ctx.state["fail"] = True
        result2 = await policy.evaluate(typing.cast(ExecutionContext, ctx))
        assert isinstance(result2, PolicyFailure)
        assert result2.reason == "configured to fail"

    asyncio.run(run_test())


def test_policy_result_immutability():
    from agnara._frozen import FrozenInstanceError

    failure = PolicyFailure(reason="error")
    with pytest.raises(FrozenInstanceError):
        failure.reason = "new error"  # type: ignore


def test_interaction_request_copies_hints_and_is_immutable():
    hints = {"impact": "destructive"}
    request = InteractionRequest(
        InteractionKind.CONFIRMATION,
        "Confirm deletion",
        "Confirm this deletion before continuing.",
        CapabilityId("accounts", "delete"),
        hints,
    )
    outcome = PolicyInteractionRequired(request)
    hints["impact"] = "safe"

    assert request.hints == {"impact": "destructive"}
    assert outcome.request is request
    with pytest.raises(FrozenInstanceError):
        request.title = "Changed"  # ty: ignore[invalid-assignment]
    with pytest.raises(TypeError):
        typing.cast(dict[str, object], request.hints)["impact"] = "safe"
