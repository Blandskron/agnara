"""E9.1: immutable hook registration and fail-fast callback configuration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.errors import DefinitionError
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    InvocationStartEvent,
    InvocationTerminalEvent,
    invoke,
)


def handler() -> str:
    return "ok"


def build(hooks: Any, *, direct: bool) -> ExecutionPlan:
    definition = CapabilityDefinition.declare(
        id=CapabilityId.parse("tests.telemetry"), handler=handler
    )
    if direct:
        return ExecutionPlan(definition=definition, target_deps={}, hooks=hooks)
    return ExecutionPlan.compile(definition, DIRegistry(), hooks=hooks)


def synchronous(event: Any) -> None:
    pass


async def coroutine(event: Any) -> None:
    pass


async def async_generator(event: Any) -> AsyncIterator[None]:
    yield None


def generator(event: Any) -> Iterator[None]:
    yield None


class AsyncCallback:
    async def __call__(self, event: Any) -> None:
        pass


class AsyncGeneratorCallback:
    async def __call__(self, event: Any) -> AsyncIterator[None]:
        yield None


class GeneratorCallback:
    def __call__(self, event: Any) -> Iterator[None]:
        yield None


@pytest.mark.parametrize("direct", [False, True], ids=["compile", "constructor"])
@pytest.mark.parametrize("method", ["on_invocation_start", "on_invocation_terminal"])
@pytest.mark.parametrize(
    "callback",
    [
        None,
        42,
        coroutine,
        async_generator,
        generator,
        AsyncCallback(),
        AsyncGeneratorCallback(),
        GeneratorCallback(),
    ],
    ids=[
        "none",
        "integer",
        "coroutine",
        "async-generator",
        "generator",
        "async-callable",
        "async-generator-callable",
        "generator-callable",
    ],
)
def test_invalid_callbacks_are_rejected_before_invocation(
    direct: bool, method: str, callback: Any
) -> None:
    hook = SimpleNamespace(on_invocation_start=synchronous, on_invocation_terminal=synchronous)
    setattr(hook, method, callback)
    with pytest.raises(DefinitionError, match=method):
        build([hook], direct=direct)


@pytest.mark.parametrize("direct", [False, True], ids=["compile", "constructor"])
@pytest.mark.parametrize("hook", [None, object(), SimpleNamespace(on_invocation_start=synchronous)])
def test_incomplete_hooks_are_rejected_at_startup(direct: bool, hook: Any) -> None:
    with pytest.raises(DefinitionError, match="hook"):
        build([hook], direct=direct)


@pytest.mark.parametrize("direct", [False, True], ids=["compile", "constructor"])
def test_source_list_mutation_cannot_change_registration_or_callback_order(direct: bool) -> None:
    calls: list[tuple[str, str]] = []

    class Hook:
        def __init__(self, name: str) -> None:
            self.name = name

        def on_invocation_start(self, event: InvocationStartEvent) -> None:
            calls.append((self.name, "start"))

        def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
            calls.append((self.name, event.outcome))

    first, second = Hook("first"), Hook("second")
    source = [first, second]
    plan = build(source, direct=direct)
    source[:] = [Hook("replacement")]
    assert plan.hooks == (first, second)
    context = ExecutionContext(
        Invocation(capability_id=plan.definition.id, payload={}, metadata={}),
        DIContainer(DIRegistry()),
    )
    assert asyncio.run(invoke(plan, context)) == "ok"
    assert calls == [
        ("first", "start"),
        ("second", "start"),
        ("first", "success"),
        ("second", "success"),
    ]


@pytest.mark.parametrize("direct", [False, True], ids=["compile", "constructor"])
def test_validation_does_not_execute_callbacks(direct: bool) -> None:
    def fail_if_called(event: Any) -> None:
        raise AssertionError("compilation must not invoke telemetry")

    hook = SimpleNamespace(
        on_invocation_start=fail_if_called, on_invocation_terminal=fail_if_called
    )
    assert build([hook], direct=direct).hooks == (hook,)
