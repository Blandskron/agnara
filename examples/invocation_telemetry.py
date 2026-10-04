"""Paired transport-neutral invocation telemetry with local observers.

Run with ``uv run python examples/invocation_telemetry.py``. See docs/TELEMETRY.md.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry
from agnara.execution import (
    CanonicalResult,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    InvocationStartEvent,
    InvocationTerminalEvent,
    Success,
    TelemetryHook,
    invoke_result,
)


class Recorder:
    """Local to one demonstration/event loop, never shared across threads.

    Real collectors own synchronization, retention, cardinality and export.
    The terminal callback tolerates a start callback that did not complete.
    """

    def __init__(self) -> None:
        self.pending: dict[str, InvocationStartEvent] = {}
        self.pairs: list[tuple[InvocationStartEvent | None, InvocationTerminalEvent]] = []

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.pending[event.invocation_id] = event

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        start = self.pending.pop(event.invocation_id, None)
        self.pairs.append((start, event))


class FailingObserver:
    """Intentional fault fixture, not a production observer template."""

    def __init__(self) -> None:
        self.starts = 0
        self.terminals = 0

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.starts += 1
        raise RuntimeError("private-observer-diagnostic")

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        self.terminals += 1
        raise RuntimeError("private-observer-diagnostic")


async def demonstrate() -> tuple[
    dict[str, CanonicalResult | str], Recorder, FailingObserver, list[str]
]:
    recorder = Recorder()
    faulty = FailingObserver()
    entered = asyncio.Event()
    effects: list[str] = []
    app = Agnara("jobs")

    @app.capability(scopes=("jobs:run",), output=str)
    async def work(action: str) -> str:
        effects.append(action)
        if action == "fail":
            raise RuntimeError("private-handler-diagnostic")
        if action == "wait":
            entered.set()
            await asyncio.Event().wait()
        return "private-result"

    dependencies = DIRegistry()
    hooks: list[TelemetryHook] = [faulty, recorder]
    plan = ExecutionPlan.compile(app.compile()["jobs.work"], dependencies, hooks=hooks)
    container = DIContainer(dependencies)
    actor = Principal("local-demo", scopes={"jobs:run"})

    async def call(
        action: Any, *, deadline: float | None = None, principal: Principal = actor
    ) -> CanonicalResult:
        return await invoke_result(
            plan,
            ExecutionContext(
                Invocation(plan.definition.id, {"action": action}, {}, deadline=deadline),
                container,
                principal=principal,
                # Deliberately repeated. Correlation labels cannot pair attempts.
                tracking_id="batch-demo",
            ),
        )

    try:
        async with asyncio.timeout(5):
            results: dict[str, CanonicalResult | str] = {
                "success": await call("private-input"),
                "denied": await call("private-input", principal=Principal("unscoped")),
                "invalid": await call(42),
                "failed": await call("fail"),
                "timeout": await call("wait", deadline=asyncio.get_running_loop().time() - 1),
            }
            entered.clear()
            async with asyncio.TaskGroup() as owned:
                caller = asyncio.current_task()
                assert caller is not None
                task = owned.create_task(call("wait"))
                await entered.wait()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    if caller.cancelling():
                        raise
                    results["cancelled"] = "CancelledError"
                else:
                    raise AssertionError("caller cancellation must propagate")
            return results, recorder, faulty, effects
    finally:
        await container.aclose()


def main() -> None:
    results, recorder, _, _ = asyncio.run(demonstrate())
    for (name, result), (_, terminal) in zip(results.items(), recorder.pairs, strict=True):
        if isinstance(result, Success):
            status = "success"
        elif isinstance(result, Failure):
            status = result.code.value
        else:
            status = result
        print(f"{name}: {status}; telemetry: {terminal.outcome}")
    attempts = {terminal.invocation_id for _, terminal in recorder.pairs}
    labels = {terminal.tracking_id for _, terminal in recorder.pairs}
    print(
        f"paired: {len(recorder.pairs)}; pending: {len(recorder.pending)}; "
        f"attempts: {len(attempts)}; correlation labels: {len(labels)}"
    )


if __name__ == "__main__":
    main()
