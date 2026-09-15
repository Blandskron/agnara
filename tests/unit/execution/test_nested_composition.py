"""ADR 0093 conformance for same-runtime nested capability invocation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from agnara import InvocationError
from agnara.capability import (
    CapabilityDefinition,
    CapabilityId,
    CapabilityRegistry,
    Confirmation,
    Idempotency,
)
from agnara.core.di import DIContainer, DIRegistry, provider
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    IdempotencyInvocation,
    IdempotencyScope,
    InMemoryIdempotencyStore,
    Invocation,
    InvocationStartEvent,
    InvocationTerminalEvent,
    Success,
    TelemetryHook,
    invoke,
)
from agnara.policy import ConfirmationEvidence, ConfirmationVerdict, Principal

OUTER = CapabilityId.parse("composition.outer")
CHILD = CapabilityId.parse("composition.child")
FOREIGN = CapabilityId.parse("foreign.child")


class Recorder(TelemetryHook):
    def __init__(self) -> None:
        self.starts: list[InvocationStartEvent] = []
        self.terminals: list[InvocationTerminalEvent] = []

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.starts.append(event)

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        self.terminals.append(event)


class Verifier:
    async def verify(self, evidence, *, capability_id, invocation, principal):
        return ConfirmationVerdict.VALID


class Resource:
    pass


class JsonCodec:
    def encode(self, value: object, /) -> bytes:
        return json.dumps(value, sort_keys=True).encode("utf-8")

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


def context(
    capability_id: CapabilityId,
    container: DIContainer,
    *,
    payload: dict[str, Any] | None = None,
    deadline: float | None = None,
    evidence: ConfirmationEvidence | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        Invocation(capability_id, payload or {}, {}, deadline),
        container,
        principal=Principal("actor", scopes={"outer:invoke"}),
        confirmation_evidence=evidence,
    )


def runtime_for(
    plans: list[ExecutionPlan],
    container: DIContainer,
    *,
    max_composition_depth: int = 8,
) -> CapabilityRuntime:
    capabilities = CapabilityRegistry(plan.definition for plan in plans).freeze()
    return CapabilityRuntime(
        capabilities,
        plans,
        container,
        max_composition_depth=max_composition_depth,
    )


def test_child_uses_compiled_plan_with_fresh_context_and_causal_telemetry() -> None:
    async def run() -> None:
        registry = DIRegistry()
        recorder = Recorder()
        child_context: ExecutionContext | None = None
        child_result: Success[str] | None = None

        def child(value: str, execution: ExecutionContext) -> str:
            nonlocal child_context
            child_context = execution
            execution.state["private"] = "child"
            return value.upper()

        async def outer(invoker: CapabilityInvoker, execution: ExecutionContext) -> str:
            nonlocal child_result
            assert execution is parent
            result = await invoker.invoke(CHILD, {"value": "nested"})
            assert isinstance(result, Success)
            child_result = result
            return result.value

        child_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=CHILD, handler=child), registry, hooks=[recorder]
        )
        outer_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=OUTER, handler=outer), registry, hooks=[recorder]
        )
        container = DIContainer(registry)
        runtime = runtime_for([outer_plan, child_plan], container)
        parent = context(OUTER, container)

        assert await runtime.invoke_result(parent) == Success("NESTED")
        assert child_context is not None
        assert child_result is not None
        assert child_context is not parent
        assert child_context.execution_id != parent.execution_id
        assert child_context.state == {"private": "child"}
        assert parent.state == {}
        assert child_context.principal is not parent.principal
        assert child_context.principal.identity == parent.principal.identity
        assert child_result.execution_id == child_context.execution_id
        assert recorder.starts[1].parent_execution_id == parent.execution_id
        assert recorder.starts[0].invocation_id != recorder.starts[1].invocation_id
        await runtime.aclose()

    asyncio.run(run())


def test_child_policy_validation_and_confirmation_are_independent() -> None:
    async def run() -> None:
        registry = DIRegistry()
        calls = 0
        seen: list[Failure] = []

        def child(value: int) -> int:
            nonlocal calls
            calls += 1
            return value

        async def outer(invoker: CapabilityInvoker) -> str:
            denied = await invoker.invoke(CHILD, {"value": "not-an-int"})
            assert isinstance(denied, Failure)
            seen.append(denied)
            return denied.code.value

        child_plan = ExecutionPlan.compile(
            CapabilityDefinition(
                id=CHILD,
                handler=child,
                scopes=frozenset({"child:invoke"}),
                confirmation=Confirmation.REQUIRED,
            ),
            registry,
            confirmation_verifier=Verifier(),
        )
        outer_plan = ExecutionPlan.compile(CapabilityDefinition(id=OUTER, handler=outer), registry)
        container = DIContainer(registry)
        runtime = runtime_for([outer_plan, child_plan], container)

        # A parent confirmation and authorization do not authorize the child.
        outcome = await runtime.invoke_result(
            context(OUTER, container, evidence=ConfirmationEvidence("parent-only"))
        )
        assert outcome == Success(FailureCode.FORBIDDEN.value)
        assert seen == [Failure(FailureCode.FORBIDDEN, "missing required scopes: child:invoke")]
        assert calls == 0
        await runtime.aclose()

    asyncio.run(run())


def test_child_confirmation_is_not_inherited_after_authorization() -> None:
    async def run() -> None:
        registry = DIRegistry()
        calls = 0

        def child() -> None:
            nonlocal calls
            calls += 1

        async def outer(invoker: CapabilityInvoker) -> FailureCode:
            result = await invoker.invoke(CHILD, {})
            assert isinstance(result, Failure)
            return result.code

        child_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=CHILD, handler=child, confirmation=Confirmation.REQUIRED),
            registry,
            confirmation_verifier=Verifier(),
        )
        outer_plan = ExecutionPlan.compile(CapabilityDefinition(id=OUTER, handler=outer), registry)
        container = DIContainer(registry)
        runtime = runtime_for([outer_plan, child_plan], container)
        outcome = await runtime.invoke_result(
            context(OUTER, container, evidence=ConfirmationEvidence("parent-only"))
        )

        assert outcome == Success(FailureCode.INTERACTION_REQUIRED)
        assert calls == 0
        await runtime.aclose()

    asyncio.run(run())


def test_child_validation_runs_after_its_own_policy_boundary() -> None:
    async def run() -> None:
        registry = DIRegistry()
        calls = 0

        def child(value: int) -> int:
            nonlocal calls
            calls += 1
            return value

        async def outer(invoker: CapabilityInvoker) -> FailureCode:
            result = await invoker.invoke(CHILD, {"value": "not-an-int"})
            assert isinstance(result, Failure)
            return result.code

        child_plan = ExecutionPlan.compile(CapabilityDefinition(id=CHILD, handler=child), registry)
        outer_plan = ExecutionPlan.compile(CapabilityDefinition(id=OUTER, handler=outer), registry)
        container = DIContainer(registry)
        runtime = runtime_for([outer_plan, child_plan], container)

        assert await runtime.invoke_result(context(OUTER, container)) == Success(
            FailureCode.INVALID_INPUT
        )
        assert calls == 0
        await runtime.aclose()

    asyncio.run(run())


def test_child_resources_close_after_success_and_failure() -> None:
    async def run() -> None:
        registry = DIRegistry()
        lifecycle: list[str] = []

        @provider()
        async def resource() -> AsyncIterator[Resource]:
            lifecycle.append("acquired")
            try:
                yield Resource()
            finally:
                lifecycle.append("released")

        registry.bind(Resource, resource)

        def child(resource: Resource, fail: bool) -> str:
            assert isinstance(resource, Resource)
            if fail:
                raise RuntimeError("child failure must be redacted")
            return "ok"

        async def outer(invoker: CapabilityInvoker) -> tuple[str, FailureCode]:
            success = await invoker.invoke(CHILD, {"fail": False})
            failure = await invoker.invoke(CHILD, {"fail": True})
            assert isinstance(success, Success)
            assert isinstance(failure, Failure)
            return success.value, failure.code

        child_plan = ExecutionPlan.compile(CapabilityDefinition(id=CHILD, handler=child), registry)
        outer_plan = ExecutionPlan.compile(CapabilityDefinition(id=OUTER, handler=outer), registry)
        container = DIContainer(registry)
        runtime = runtime_for([outer_plan, child_plan], container)

        assert await runtime.invoke_result(context(OUTER, container)) == Success(
            ("ok", FailureCode.INTERNAL_FAILURE)
        )
        assert lifecycle == ["acquired", "released", "acquired", "released"]
        await runtime.aclose()

    asyncio.run(run())


def test_child_deadline_and_cancellation_preserve_lifecycle_ownership() -> None:
    async def run() -> None:
        registry = DIRegistry()
        acquired = released = calls = 0
        started = asyncio.Event()

        @provider()
        async def resource() -> AsyncIterator[Resource]:
            nonlocal acquired, released
            acquired += 1
            try:
                yield Resource()
            finally:
                released += 1

        registry.bind(Resource, resource)

        async def child(resource: Resource) -> None:
            nonlocal calls
            calls += 1
            started.set()
            await asyncio.Event().wait()

        async def outer(invoker: CapabilityInvoker) -> None:
            await invoker.invoke(CHILD, {})

        child_plan = ExecutionPlan.compile(CapabilityDefinition(id=CHILD, handler=child), registry)
        outer_plan = ExecutionPlan.compile(CapabilityDefinition(id=OUTER, handler=outer), registry)
        container = DIContainer(registry)
        runtime = runtime_for([outer_plan, child_plan], container)

        task = asyncio.create_task(runtime.invoke_result(context(OUTER, container)))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (acquired, released, calls) == (1, 1, 1)

        async def timed_outer(invoker: CapabilityInvoker) -> FailureCode:
            result = await invoker.invoke(CHILD, {}, timeout=0)
            assert isinstance(result, Failure)
            return result.code

        timed_outer_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=OUTER, handler=timed_outer), registry
        )
        timed_runtime = runtime_for([timed_outer_plan, child_plan], container)
        assert await timed_runtime.invoke_result(context(OUTER, container)) == Success(
            FailureCode.TIMEOUT
        )
        assert calls == 1
        await runtime.aclose()

    asyncio.run(run())


def test_recursion_depth_and_foreign_target_are_refused_before_effects() -> None:
    async def run() -> None:
        registry = DIRegistry()
        calls = 0

        async def outer(invoker: CapabilityInvoker) -> FailureCode:
            nonlocal calls
            calls += 1
            result = await invoker.invoke(OUTER, {})
            assert isinstance(result, Failure)
            return result.code

        def foreign() -> None:
            nonlocal calls
            calls += 100

        outer_plan = ExecutionPlan.compile(CapabilityDefinition(id=OUTER, handler=outer), registry)
        foreign_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=FOREIGN, handler=foreign), registry
        )
        container = DIContainer(registry)
        runtime = runtime_for([outer_plan], container, max_composition_depth=1)
        assert await runtime.invoke_result(context(OUTER, container)) == Success(
            FailureCode.CONFLICT
        )
        assert calls == 1

        async def foreign_outer(invoker: CapabilityInvoker) -> FailureCode:
            result = await invoker.invoke(FOREIGN, {})
            assert isinstance(result, Failure)
            return result.code

        foreign_outer_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=OUTER, handler=foreign_outer), registry
        )
        foreign_runtime = runtime_for([foreign_outer_plan], container)
        assert await foreign_runtime.invoke_result(context(OUTER, container)) == Success(
            FailureCode.NOT_FOUND
        )
        assert calls == 1
        assert foreign_plan.definition.id not in foreign_runtime._plans
        foreign_snapshot = CapabilityRegistry([foreign_plan.definition]).freeze()
        with pytest.raises(InvocationError, match="does not belong to this capability snapshot"):
            CapabilityRuntime(foreign_snapshot, [outer_plan], container)
        await runtime.aclose()

    asyncio.run(run())


def test_direct_invocation_without_composition_remains_unchanged() -> None:
    async def run() -> None:
        registry = DIRegistry()
        plan = ExecutionPlan.compile(
            CapabilityDefinition(id=OUTER, handler=lambda: "direct"), registry
        )
        direct_context = context(OUTER, DIContainer(registry))
        assert await invoke(plan, direct_context) == "direct"

    asyncio.run(run())


def test_child_does_not_inherit_parent_idempotency_or_run_a_stream_target() -> None:
    async def run() -> None:
        registry = DIRegistry()
        observed: list[object] = []
        stream_started = False

        def child(execution: ExecutionContext) -> str:
            observed.append(execution.idempotency)
            return "child"

        async def rows():
            nonlocal stream_started
            stream_started = True
            yield "row"

        async def outer(invoker: CapabilityInvoker) -> tuple[FailureCode, str]:
            stream = await invoker.invoke(FOREIGN, {})
            child_result = await invoker.invoke(CHILD, {})
            assert isinstance(stream, Failure)
            assert isinstance(child_result, Success)
            return stream.code, child_result.value

        child_plan = ExecutionPlan.compile(CapabilityDefinition(id=CHILD, handler=child), registry)
        stream_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=FOREIGN, handler=rows, streaming=True), registry
        )
        outer_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=OUTER, handler=outer, idempotency=Idempotency.YES), registry
        )
        container = DIContainer(registry)
        runtime = runtime_for([outer_plan, child_plan, stream_plan], container)
        parent_principal = Principal("actor", scopes={"outer:invoke"})
        scope = IdempotencyScope(OUTER, parent_principal.identity, "outer-key", b"outer")
        parent = ExecutionContext(
            Invocation(OUTER, {}, {}),
            container,
            principal=parent_principal,
            idempotency=IdempotencyInvocation(
                scope,
                InMemoryIdempotencyStore(),
                JsonCodec(),
                30,
                60,
            ),
        )

        assert await runtime.invoke_result(parent) == Success(
            (FailureCode.INTERNAL_FAILURE, "child")
        )
        assert observed == [None]
        assert stream_started is False
        await runtime.aclose()

    asyncio.run(run())


def test_concurrent_parents_do_not_share_child_ancestry_or_context() -> None:
    async def run() -> None:
        registry = DIRegistry()

        async def child(execution: ExecutionContext) -> str:
            await asyncio.sleep(0)
            return execution.execution_id

        async def outer(invoker: CapabilityInvoker) -> str:
            result = await invoker.invoke(CHILD, {})
            assert isinstance(result, Success)
            return result.value

        child_plan = ExecutionPlan.compile(CapabilityDefinition(id=CHILD, handler=child), registry)
        outer_plan = ExecutionPlan.compile(CapabilityDefinition(id=OUTER, handler=outer), registry)
        container = DIContainer(registry)
        runtime = runtime_for([outer_plan, child_plan], container)
        parents = [context(OUTER, container) for _ in range(20)]
        outcomes = await asyncio.gather(*(runtime.invoke_result(parent) for parent in parents))

        child_ids = {outcome.value for outcome in outcomes if isinstance(outcome, Success)}
        assert len(child_ids) == 20
        assert child_ids.isdisjoint({parent.execution_id for parent in parents})
        await runtime.aclose()

    asyncio.run(run())
