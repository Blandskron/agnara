"""Installed-artifact consumer for standalone Agnara semantics.

This module is intentionally self-contained so the dogfooding test can copy it
outside the checkout and execute it under ``python -I``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from agnara import Agnara, App, CapabilityId, Principal
from agnara.di import DIContainer, DIRegistry
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    IdempotencyInvocation,
    IdempotencyScope,
    InMemoryIdempotencyStore,
    Invocation,
    InvocationStartEvent,
    InvocationTerminalEvent,
    StreamInterrupted,
    StreamTerminal,
    Success,
    open_stream,
)


class JsonCodec:
    def encode(self, value: object, /) -> bytes:
        return json.dumps(value).encode()

    def decode(self, payload: bytes, /) -> object:
        return json.loads(payload)


class Recorder:
    def __init__(self) -> None:
        self.starts: list[InvocationStartEvent] = []
        self.terminals: list[InvocationTerminalEvent] = []

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.starts.append(event)

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        self.terminals.append(event)


async def main() -> None:
    effects = 0
    cancelled = 0
    application = Agnara("dogfood_standalone")
    app = App("orders")

    @app.capability
    def echo(value: str) -> str:
        return f"echo:{value}"

    @app.capability
    async def compose(invoker: CapabilityInvoker) -> str:
        result = await invoker.invoke(CapabilityId.parse("orders.echo"), {"value": "child"})
        assert isinstance(result, Success)
        return f"composed:{result.value}"

    @app.capability(idempotent=True)
    def idempotent_write() -> int:
        nonlocal effects
        effects += 1
        return effects

    @app.capability(idempotent=False)
    def non_idempotent_write() -> int:
        nonlocal effects
        effects += 1
        return effects

    @app.capability(streaming=True, output=int)
    async def partial_failure() -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("consumer-visible secret must be redacted")

    @app.capability(streaming=True, output=str)
    async def cancellable() -> AsyncIterator[str]:
        nonlocal cancelled
        try:
            yield "opened"
            await asyncio.Event().wait()
        finally:
            cancelled += 1

    application.include(app)
    capabilities = application.compile()
    registry = DIRegistry()
    recorder = Recorder()
    plans = {
        str(identifier): ExecutionPlan.compile(definition, registry, hooks=(recorder,))
        for identifier, definition in capabilities.items()
    }
    container = DIContainer(registry)
    runtime = CapabilityRuntime(capabilities, tuple(plans.values()), container)
    principal = Principal("consumer", scopes=())

    def context(name: str, payload: dict[str, object] | None = None) -> ExecutionContext:
        return ExecutionContext(
            Invocation(CapabilityId.parse(name), payload or {}, {}), container, principal=principal
        )

    try:
        composed = await runtime.invoke_result(context("orders.compose"))
        assert isinstance(composed, Success) and composed.value == "composed:echo:child"

        store = InMemoryIdempotencyStore()
        selector = IdempotencyInvocation(
            IdempotencyScope(
                CapabilityId.parse("orders.idempotent_write"), "consumer", "capture-1", b"v1"
            ),
            store,
            JsonCodec(),
            10,
            30,
        )
        first_context = context("orders.idempotent_write")
        first_context = ExecutionContext(
            first_context.invocation, container, principal=principal, idempotency=selector
        )
        first = await runtime.invoke_result(first_context)
        second_context = ExecutionContext(
            Invocation(CapabilityId.parse("orders.idempotent_write"), {}, {}),
            container,
            principal=principal,
            idempotency=selector,
        )
        second = await runtime.invoke_result(second_context)
        assert isinstance(first, Success) and isinstance(second, Success)
        assert first.value == second.value == 1
        assert first_context.execution_id == second_context.execution_id

        plain_one = await runtime.invoke_result(context("orders.non_idempotent_write"))
        plain_two = await runtime.invoke_result(context("orders.non_idempotent_write"))
        assert isinstance(plain_one, Success) and isinstance(plain_two, Success)
        assert (plain_one.value, plain_two.value) == (2, 3)

        async with open_stream(
            plans["orders.partial_failure"], context("orders.partial_failure")
        ) as stream:
            assert await anext(stream) == 1
            try:
                await anext(stream)
            except StreamInterrupted as interrupted:
                assert interrupted.units_emitted == 1
                assert "secret" not in interrupted.failure.message
            else:  # pragma: no cover - an interruption is the contract under test
                raise AssertionError("post-partial failure must interrupt the stream")
            assert stream.terminal is StreamTerminal.INTERRUPTED

        async def consume_then_cancel() -> None:
            async with open_stream(
                plans["orders.cancellable"], context("orders.cancellable")
            ) as stream:
                assert await anext(stream) == "opened"
                await anext(stream)

        task = asyncio.create_task(consume_then_cancel())
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:  # pragma: no cover - cancellation must propagate to the caller
            raise AssertionError("consumer cancellation must propagate")
        assert cancelled == 1

        assert recorder.starts and recorder.terminals
        assert all(event.execution_id for event in recorder.starts)
        assert {event.invocation_id for event in recorder.starts} == {
            event.invocation_id for event in recorder.terminals
        }
    finally:
        await runtime.aclose()

    print("STANDALONE_DOGFOOD_OK")


if __name__ == "__main__":
    asyncio.run(main())
