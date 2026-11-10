"""Owned direct Python streams; run with uv run python examples/direct_streaming.py.

See docs/DIRECT_STREAMING.md. All resources and principals are local fixtures.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

from agnara import Agnara, PolicyDeniedError, Principal, ValidationError
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    StreamInterrupted,
    StreamTerminal,
    open_stream,
)


class ReportSession:
    """Invocation-owned fixture, without a database or external effects."""


@dataclass(frozen=True)
class Observation:
    units: tuple[int, ...]
    terminal: StreamTerminal | None
    failure: Failure | None
    refusal: str | None
    units_emitted: int
    events: tuple[str, ...]


async def run_case(
    mode: str, *, waiting: asyncio.Event | None = None, events: list[str] | None = None
) -> Observation:
    """Own one stream and its container on the calling task and event loop.

    The optional event lets a caller cancel the blocked-producer case without
    sleeps. The caller can retain the event list to observe cleanup even when
    cancellation propagates instead of returning an Observation.
    """
    if events is None:
        events = []
    app = Agnara("reports")

    @provider(scope=Scope.INVOCATION)
    async def provide_session() -> AsyncIterator[ReportSession]:
        events.append("session.open")
        try:
            yield ReportSession()
        finally:
            events.append("session.close")

    @app.capability(streaming=True, output=int, scopes=("reports:read",))
    async def rows(count: int, session: ReportSession) -> AsyncIterator[int]:
        events.append("producer.open")
        try:
            if mode == "first_failure":
                raise RuntimeError("demo-private-diagnostic")
            for number in range(count):
                if mode == "cancelled":
                    if waiting is not None:
                        waiting.set()
                    await asyncio.Event().wait()
                events.append(f"produce:{number}")
                if mode == "invalid_output" and number == 1:
                    # Deliberately violate output=int to demonstrate rejection.
                    yield cast(int, "demo-private-output")
                else:
                    yield number
                if mode == "late_failure":
                    raise RuntimeError("demo-private-diagnostic")
        finally:
            events.append("producer.close")

    dependencies = DIRegistry()
    dependencies.bind(ReportSession, provide_session)
    plan = ExecutionPlan.compile(app.compile()["reports.rows"], dependencies)
    container = DIContainer(dependencies)
    principal = Principal("local-demo", scopes=set() if mode == "denied" else {"reports:read"})
    context = ExecutionContext(
        Invocation(plan.definition.id, {"count": "bad" if mode == "invalid_input" else 2}, {}),
        container,
        principal=principal,
    )
    stream = open_stream(plan, context)
    events.append("consumer.created")  # open_stream has acquired nothing.
    units: list[int] = []
    failure: Failure | None = None
    refusal: str | None = None
    try:
        async with stream:
            events.append("consumer.entered")  # DI opened; producer has not run.
            async for unit in stream:
                units.append(unit)
                events.append(f"consume:{unit}")
                if mode == "abandoned":
                    break  # Exiting the context closes the unexhausted producer.
    except PolicyDeniedError:
        refusal = "forbidden"
    except ValidationError:
        refusal = "invalid_input"
    except StreamInterrupted as error:
        failure = error.failure
        assert error.units_emitted == len(units)
    finally:
        await container.aclose()
    return Observation(
        tuple(units), stream.terminal, failure, refusal, stream.units_emitted, tuple(events)
    )


async def demonstrate() -> dict[str, Observation]:
    async with asyncio.timeout(5):
        return {
            mode: await run_case(mode)
            for mode in (
                "completed",
                "abandoned",
                "denied",
                "invalid_input",
                "first_failure",
                "late_failure",
                "invalid_output",
            )
        }


def main() -> None:
    for name, result in asyncio.run(demonstrate()).items():
        terminal = result.terminal.value if result.terminal is not None else "not_started"
        failure = result.failure.code.value if result.failure is not None else result.refusal
        print(f"{name}: units={list(result.units)} terminal={terminal} failure={failure}")


if __name__ == "__main__":
    main()
