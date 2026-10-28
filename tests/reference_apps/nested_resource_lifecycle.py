"""Public-API nested resource consumer, copied outside the checkout for wheel tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Literal, cast

from agnara import Agnara, CapabilityId, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
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

type Case = Literal[
    "success",
    "handler_failure",
    "invalid_output",
    "invalid_input",
    "child_denied",
    "parent_denied",
    "cancelled",
]
CASES: tuple[Case, ...] = (
    "success",
    "handler_failure",
    "invalid_output",
    "invalid_input",
    "child_denied",
    "parent_denied",
    "cancelled",
)


class Session:
    def __init__(self, number: int) -> None:
        self.number = number
        self.closed = False


class Shared:
    def __init__(self) -> None:
        self.closed = False


async def run_case(case: Case) -> None:
    """Observe real compiled execution, including cleanup before runtime shutdown."""
    before = asyncio.all_tasks()
    loop = asyncio.get_running_loop()
    events: list[str] = []
    singleton_events: list[str] = []
    sessions: list[Session] = []
    shared_instances: list[Shared] = []
    child_contexts: list[ExecutionContext] = []
    child_resources: list[tuple[Session, Shared]] = []
    child_initial_states: list[dict[str, object]] = []
    child_resources_active: list[bool] = []
    entered = asyncio.Event()
    app = Agnara("artifact_lifetimes")

    @provider(scope=Scope.INVOCATION)
    async def session_provider() -> AsyncIterator[Session]:
        resource = Session(len(sessions) + 1)
        sessions.append(resource)
        events.append(f"scope.{resource.number}.open")
        try:
            yield resource
        finally:
            assert asyncio.get_running_loop() is loop
            assert not resource.closed, "invocation resource closed twice"
            resource.closed = True
            events.append(f"scope.{resource.number}.close")

    @provider(scope=Scope.SINGLETON)
    async def shared_provider() -> AsyncIterator[Shared]:
        resource = Shared()
        shared_instances.append(resource)
        singleton_events.append("open")
        try:
            yield resource
        finally:
            assert asyncio.get_running_loop() is loop
            assert not resource.closed, "singleton closed twice"
            resource.closed = True
            singleton_events.append("close")

    @app.capability(scopes=("child:read",), output=int)
    async def child(
        value: int, session: Session, shared: Shared, execution: ExecutionContext
    ) -> int:
        child_contexts.append(execution)
        child_resources.append((session, shared))
        child_initial_states.append(dict(execution.state))
        child_resources_active.append(
            not session.closed and not sessions[0].closed and not shared.closed
        )
        events.append("child.enter")
        try:
            execution.state["private"] = "child"
            execution.principal.metadata["child"] = "detached"
            entered.set()
            if case == "cancelled":
                await asyncio.Event().wait()
            if case == "handler_failure":
                raise RuntimeError("fixture-private-diagnostic")
            if case == "invalid_output":
                return cast(int, "fixture-private-output")
            return value
        finally:
            events.append("child.exit")

    @app.capability(scopes=("parent:read",), output=str)
    async def parent(
        session: Session, shared: Shared, invoker: CapabilityInvoker, execution: ExecutionContext
    ) -> str:
        assert execution is root
        assert session is sessions[0] and not session.closed
        assert shared is shared_instances[0] and not shared.closed
        root.state["private"] = "parent"
        events.append("parent.enter")
        try:
            value = "invalid" if case in {"invalid_input", "child_denied"} else 7
            result = await invoker.invoke(
                CapabilityId.parse("artifact_lifetimes.child"), {"value": value}
            )
            events.append("parent.resume")
            assert not session.closed and not shared.closed
            assert all(resource.closed for resource in sessions[1:])
            assert root.state == {"private": "parent"}
            assert root.principal.metadata == {"authenticated": "fixture"}
            assert result.execution_id and result.execution_id != root.execution_id
            if child_contexts:
                assert result.execution_id == child_contexts[0].execution_id
            if isinstance(result, Failure):
                expected_code = {
                    "handler_failure": FailureCode.INTERNAL_FAILURE,
                    "invalid_output": FailureCode.INTERNAL_FAILURE,
                    "invalid_input": FailureCode.INVALID_INPUT,
                    "child_denied": FailureCode.FORBIDDEN,
                }[case]
                assert result.code is expected_code, result
                assert "fixture-private" not in repr(result)
                return f"child:{result.code.value}"
            assert result == Success(7), result
            return f"child:{result.value}"
        finally:
            events.append("parent.exit")

    dependencies = DIRegistry()
    dependencies.bind(Session, session_provider)
    dependencies.bind(Shared, shared_provider)
    capabilities = app.compile()
    plans = [ExecutionPlan.compile(capabilities[key], dependencies) for key in capabilities]
    container = DIContainer(dependencies)
    runtime = CapabilityRuntime(capabilities, plans, container)
    scopes = {"parent:read", "child:read"}
    if case == "child_denied":
        scopes.remove("child:read")
    elif case == "parent_denied":
        scopes.remove("parent:read")
    root = ExecutionContext(
        Invocation(CapabilityId.parse("artifact_lifetimes.parent"), {}, {}),
        container,
        principal=Principal("fixture-actor", scopes=scopes, metadata={"authenticated": "fixture"}),
    )
    try:
        async with asyncio.timeout(10):
            if case == "cancelled":
                async with asyncio.TaskGroup() as tasks:
                    task = tasks.create_task(runtime.invoke_result(root))
                    await entered.wait()  # Child and both resources are active.
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    else:
                        raise AssertionError("nested cancellation did not propagate")
            else:
                result = await runtime.invoke_result(root)
                assert result.execution_id == root.execution_id and result.execution_id
                if case == "parent_denied":
                    assert isinstance(result, Failure) and result.code is FailureCode.FORBIDDEN
                else:
                    expected_value = {
                        "success": "child:7",
                        "handler_failure": "child:internal_failure",
                        "invalid_output": "child:internal_failure",
                        "invalid_input": "child:invalid_input",
                        "child_denied": "child:forbidden",
                    }[case]
                    assert result == Success(expected_value), result

        expected_events = ["scope.1.open", "parent.enter"]
        child_ran = case in {"success", "handler_failure", "invalid_output", "cancelled"}
        if child_ran:
            expected_events += ["scope.2.open", "child.enter", "child.exit", "scope.2.close"]
        if case != "cancelled":
            expected_events.append("parent.resume")
        expected_events += ["parent.exit", "scope.1.close"]
        assert events == ([] if case == "parent_denied" else expected_events), events
        assert len(sessions) == (0 if case == "parent_denied" else 2 if child_ran else 1)
        assert len(child_contexts) == int(child_ran)
        if child_ran:
            child_context = child_contexts[0]
            assert child_context is not root
            assert child_context.execution_id and child_context.execution_id != root.execution_id
            assert child_initial_states == [{}]
            assert child_context.state == {"private": "child"}
            assert root.state == {"private": "parent"}
            assert child_context.principal is not root.principal
            assert child_context.principal.identity == root.principal.identity == "fixture-actor"
            assert child_context.principal.scopes == root.principal.scopes
            assert child_context.principal.metadata == {
                "authenticated": "fixture",
                "child": "detached",
            }
            assert root.principal.metadata == {"authenticated": "fixture"}
            child_session, child_shared = child_resources[0]
            assert child_session is sessions[1] and child_session is not sessions[0]
            assert child_shared is shared_instances[0]
            assert child_resources_active == [True]
        assert all(resource.closed for resource in sessions)
        assert singleton_events == ([] if case == "parent_denied" else ["open"])
        assert len(shared_instances) == int(case != "parent_denied")
        assert all(not resource.closed for resource in shared_instances)
    finally:
        await runtime.aclose()
    assert singleton_events == ([] if case == "parent_denied" else ["open", "close"])
    assert all(resource.closed for resource in shared_instances)
    assert asyncio.all_tasks() == before, "consumer left tasks running"


async def main() -> None:
    for case in CASES:
        await run_case(case)
    print("NESTED_RESOURCE_LIFECYCLE_ARTIFACT_OK")


if __name__ == "__main__":
    asyncio.run(main())
