import asyncio
import typing

import pytest

from agnara.execution.context import ExecutionContext
from agnara.policy.base import Policy, PolicyFailure, PolicyResult, PolicySuccess


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
