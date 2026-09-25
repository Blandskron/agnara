"""Direct-runtime conformance for ADR 0093 composition boundaries.

The scenarios use only the transport-neutral public runtime surface so an
embedded host can reuse their setup without importing a protocol adapter.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from agnara import InvocationError
from agnara.capability import (
    CapabilityDefinition,
    CapabilityId,
    CapabilityRegistry,
    Idempotency,
)
from agnara.core.di import DIContainer, DIRegistry
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
    Success,
    open_stream,
)
from agnara.policy import Principal

OUTER = CapabilityId.parse("composition.outer")
CHILD = CapabilityId.parse("composition.child")
STREAM = CapabilityId.parse("composition.stream")


class JsonCodec:
    def encode(self, value: object, /) -> bytes:
        return json.dumps(value, sort_keys=True).encode("utf-8")

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


def test_composition_refuses_streaming_children_and_streaming_parents_before_start() -> None:
    async def run() -> None:
        child_started = False
        parent_started = False
        registry = DIRegistry()

        async def stream_child():
            nonlocal child_started
            child_started = True
            yield "unreachable"

        async def outer(invoker: CapabilityInvoker) -> FailureCode:
            result = await invoker.invoke(STREAM, {})
            assert isinstance(result, Failure)
            return result.code

        async def stream_parent(invoker: CapabilityInvoker):
            nonlocal parent_started
            parent_started = True
            yield invoker

        child_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=STREAM, handler=stream_child, streaming=True), registry
        )
        outer_plan = ExecutionPlan.compile(CapabilityDefinition(id=OUTER, handler=outer), registry)
        container = DIContainer(registry)
        runtime = CapabilityRuntime(
            CapabilityRegistry([outer_plan.definition, child_plan.definition]).freeze(),
            [outer_plan, child_plan],
            container,
        )

        assert await runtime.invoke_result(
            ExecutionContext(Invocation(OUTER, {}, {}), container)
        ) == Success(FailureCode.CONFLICT)
        assert child_started is False

        stream_parent_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=CHILD, handler=stream_parent, streaming=True), registry
        )
        stream_context = ExecutionContext(Invocation(CHILD, {}, {}), container)
        with pytest.raises(InvocationError, match="complete-result semantics"):
            async with open_stream(stream_parent_plan, stream_context):
                pass
        assert parent_started is False
        await runtime.aclose()

    asyncio.run(run())


def test_nested_idempotency_never_reuses_a_parent_selector_as_a_child_selector() -> None:
    async def run() -> None:
        effects = 0
        child_idempotency: list[object] = []
        registry = DIRegistry()
        store = InMemoryIdempotencyStore()

        def child(execution: ExecutionContext) -> int:
            nonlocal effects
            child_idempotency.append(execution.idempotency)
            effects += 1
            return effects

        async def outer(invoker: CapabilityInvoker):
            result = await invoker.invoke(CHILD, {})
            if isinstance(result, Failure):
                return result
            return result.value

        child_plan = ExecutionPlan.compile(
            CapabilityDefinition(
                id=CHILD,
                handler=child,
                idempotency=Idempotency.YES,
                scopes=frozenset({"child:invoke"}),
            ),
            registry,
        )
        outer_plan = ExecutionPlan.compile(
            CapabilityDefinition(
                id=OUTER,
                handler=outer,
                idempotency=Idempotency.YES,
                scopes=frozenset({"outer:invoke"}),
            ),
            registry,
        )
        container = DIContainer(registry)
        runtime = CapabilityRuntime(
            CapabilityRegistry([outer_plan.definition, child_plan.definition]).freeze(),
            [outer_plan, child_plan],
            container,
        )

        def context(key: str, scopes: frozenset[str]) -> ExecutionContext:
            principal = Principal("actor", scopes=scopes)
            return ExecutionContext(
                Invocation(OUTER, {}, {}),
                container,
                principal=principal,
                idempotency=IdempotencyInvocation(
                    IdempotencyScope(OUTER, principal.identity, key, b"outer-request"),
                    store,
                    JsonCodec(),
                    30,
                    60,
                ),
            )

        permitted = frozenset({"outer:invoke", "child:invoke"})
        assert await runtime.invoke_result(context("outer-one", permitted)) == Success(1)
        # The outer result is reused, so its child is never re-entered; that is
        # outer-capability reuse, not an inherited child idempotency selector.
        assert await runtime.invoke_result(context("outer-one", permitted)) == Success(1)
        assert await runtime.invoke_result(context("outer-two", permitted)) == Success(2)
        assert child_idempotency == [None, None]
        assert effects == 2

        # A fresh outer selector executes the child again, where the child's
        # own policy still decides authority before its effects.
        denied = await runtime.invoke_result(context("outer-three", frozenset({"outer:invoke"})))
        assert denied == Failure(FailureCode.FORBIDDEN, "required scopes not granted")
        assert effects == 2
        await runtime.aclose()

    asyncio.run(run())


def test_indirect_cycles_and_depth_limits_refuse_before_next_effect() -> None:
    async def run() -> None:
        registry = DIRegistry()
        middle = CapabilityId.parse("composition.middle")
        leaf = CapabilityId.parse("composition.leaf")
        blocked = CapabilityId.parse("composition.blocked")
        effects: list[CapabilityId] = []

        async def outer(invoker: CapabilityInvoker) -> FailureCode:
            effects.append(OUTER)
            result = await invoker.invoke(middle, {})
            assert isinstance(result, Success)
            return result.value

        async def middle_handler(invoker: CapabilityInvoker) -> FailureCode:
            effects.append(middle)
            result = await invoker.invoke(leaf, {})
            assert isinstance(result, Success)
            return result.value

        async def leaf_handler(invoker: CapabilityInvoker) -> FailureCode:
            effects.append(leaf)
            result = await invoker.invoke(blocked, {})
            assert isinstance(result, Failure)
            return result.code

        def blocked_handler() -> None:
            effects.append(blocked)

        outer_plan = ExecutionPlan.compile(CapabilityDefinition(id=OUTER, handler=outer), registry)
        middle_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=middle, handler=middle_handler), registry
        )
        leaf_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=leaf, handler=leaf_handler), registry
        )
        blocked_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=blocked, handler=blocked_handler), registry
        )
        container = DIContainer(registry)
        runtime = CapabilityRuntime(
            CapabilityRegistry(
                [
                    outer_plan.definition,
                    middle_plan.definition,
                    leaf_plan.definition,
                    blocked_plan.definition,
                ]
            ).freeze(),
            [outer_plan, middle_plan, leaf_plan, blocked_plan],
            container,
            max_composition_depth=2,
        )

        assert await runtime.invoke_result(
            ExecutionContext(Invocation(OUTER, {}, {}), container)
        ) == Success(FailureCode.CONFLICT)
        assert effects == [OUTER, middle, leaf]
        await runtime.aclose()

    asyncio.run(run())


def test_indirect_cycle_refuses_before_reentering_the_first_capability() -> None:
    async def run() -> None:
        registry = DIRegistry()
        middle = CapabilityId.parse("composition.middle")
        effects: list[CapabilityId] = []

        async def outer(invoker: CapabilityInvoker) -> FailureCode:
            effects.append(OUTER)
            result = await invoker.invoke(middle, {})
            assert isinstance(result, Success)
            return result.value

        async def middle_handler(invoker: CapabilityInvoker) -> FailureCode:
            effects.append(middle)
            result = await invoker.invoke(OUTER, {})
            assert isinstance(result, Failure)
            return result.code

        outer_plan = ExecutionPlan.compile(CapabilityDefinition(id=OUTER, handler=outer), registry)
        middle_plan = ExecutionPlan.compile(
            CapabilityDefinition(id=middle, handler=middle_handler), registry
        )
        container = DIContainer(registry)
        runtime = CapabilityRuntime(
            CapabilityRegistry([outer_plan.definition, middle_plan.definition]).freeze(),
            [outer_plan, middle_plan],
            container,
        )

        assert await runtime.invoke_result(
            ExecutionContext(Invocation(OUTER, {}, {}), container)
        ) == Success(FailureCode.CONFLICT)
        assert effects == [OUTER, middle]
        await runtime.aclose()

    asyncio.run(run())
