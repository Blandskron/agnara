"""Owned direct invocation deadlines and cancellation.

Run with ``uv run python examples/deadlines.py``. See docs/DEADLINES.md.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    CanonicalResult,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    Success,
    invoke_result,
)


class Session:
    """Invocation-owned fixture; no database or external effects."""


async def demonstrate() -> tuple[dict[str, CanonicalResult | str], list[str]]:
    # Mutable fixtures belong to this call and this event loop only.
    events: list[str] = []
    entered = asyncio.Event()
    release = asyncio.Event()
    app = Agnara("jobs")

    @provider(scope=Scope.INVOCATION)
    async def provide_session() -> AsyncIterator[Session]:
        events.append("session.open")
        try:
            yield Session()
        finally:
            # Await a ready event to demonstrate async teardown without sleeps.
            await release.wait()
            events.append("session.close")

    @app.capability(scopes=("jobs:run",), output=str)
    async def work(wait: bool, session: Session) -> str:
        events.append("handler.enter")
        try:
            if wait:
                entered.set()
                await asyncio.Event().wait()
            return "done"
        finally:
            events.append("handler.exit")

    dependencies = DIRegistry()
    dependencies.bind(Session, provide_session)
    plan = ExecutionPlan.compile(app.compile()["jobs.work"], dependencies)
    container = DIContainer(dependencies)
    actor = Principal("local-demo", scopes={"jobs:run"})
    loop = asyncio.get_running_loop()
    release.set()

    async def call(
        *, wait: bool, deadline: float | None = None, principal: Principal = actor
    ) -> CanonicalResult:
        return await invoke_result(
            plan,
            ExecutionContext(
                Invocation(plan.definition.id, {"wait": wait}, {}, deadline=deadline),
                container,
                principal=principal,
            ),
        )

    try:
        # A watchdog bounds the demonstration; it is separate from each
        # invocation's deadline and is not its canonical timeout result.
        async with asyncio.timeout(5):
            results: dict[str, CanonicalResult | str] = {
                "success": await call(wait=False, deadline=loop.time() + 60),
                "denied": await call(wait=False, principal=Principal("unscoped")),
            }
            # An already-expired direct deadline delivers cancellation at the
            # first suspension; it does not prevent synchronous entry work.
            results["timeout"] = await call(wait=True, deadline=loop.time() - 1)
            entered.clear()
            async with asyncio.TaskGroup() as owned:
                caller = asyncio.current_task()
                assert caller is not None
                task = owned.create_task(call(wait=True))
                await entered.wait()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    # Handle the child cancellation we requested, while
                    # preserving cancellation of the demonstration itself.
                    if caller.cancelling():
                        raise
                    results["cancelled"] = "CancelledError"
                else:
                    raise AssertionError("caller cancellation must propagate")
            assert task.cancelled()
            return results, events
    finally:
        await container.aclose()


def main() -> None:
    results, events = asyncio.run(demonstrate())
    for name, result in results.items():
        if isinstance(result, Success):
            print(f"{name}: {result.value}")
        elif isinstance(result, Failure):
            print(f"{name}: {result.code.value}")
        else:
            print(f"{name}: {result}")
    print(f"events: {events}")


if __name__ == "__main__":
    main()
