"""Check the unchanged direct streaming tutorial against installed candidate wheels."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

from agnara.execution import Failure, FailureCode, StreamTerminal

ENTRY = ("consumer.created", "session.open", "consumer.entered", "producer.open")
CLOSE = ("producer.close", "session.close")
FIRST = ("produce:0", "consume:0")
CASES = {
    "completed": (
        (0, 1),
        StreamTerminal.COMPLETED,
        None,
        ENTRY + FIRST + ("produce:1", "consume:1") + CLOSE,
    ),
    "abandoned": ((0,), StreamTerminal.ABANDONED, None, ENTRY + FIRST + CLOSE),
    "denied": ((), None, "forbidden", ("consumer.created",)),
    "invalid_input": ((), None, "invalid_input", ("consumer.created",)),
    "first_failure": ((), StreamTerminal.INTERRUPTED, None, ENTRY + CLOSE),
    "late_failure": ((0,), StreamTerminal.INTERRUPTED, None, ENTRY + FIRST + CLOSE),
    "invalid_output": (
        (0,),
        StreamTerminal.INTERRUPTED,
        None,
        ENTRY + FIRST + ("produce:1",) + CLOSE,
    ),
}


def validate(demo: Any) -> None:
    outcomes, cancelled_events = demo
    assert list(outcomes) == list(CASES)
    for name, (units, terminal, refusal, events) in CASES.items():
        result = outcomes[name]
        assert type(result.units) is tuple and result.units == units, name
        assert all(type(unit) is int for unit in result.units), name
        assert type(result.units_emitted) is int and result.units_emitted == len(units), name
        assert result.terminal is terminal and result.refusal == refusal, name
        assert type(result.events) is tuple and result.events == events, name
        if terminal is StreamTerminal.INTERRUPTED:
            assert isinstance(result.failure, Failure), name
            assert result.failure.code is FailureCode.INTERNAL_FAILURE, name
            assert result.failure == Failure(
                FailureCode.INTERNAL_FAILURE, "capability invocation failed"
            ), name
        else:
            assert result.failure is None, name
    assert type(cancelled_events) is tuple and cancelled_events == ENTRY + CLOSE


async def run_guide(path: Path) -> Any:
    name = "_agnara_direct_streaming_guide_consumer"
    assert name not in sys.modules
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # Deferred dataclass annotations need the real module.
    before = asyncio.all_tasks()
    try:
        spec.loader.exec_module(module)
        async with asyncio.timeout(20):
            outcomes = await module.demonstrate()
            assert asyncio.all_tasks() == before, "guide tasks survived"
            waiting = asyncio.Event()
            events: list[str] = []
            async with asyncio.TaskGroup() as owned:
                task = owned.create_task(
                    module.run_case("cancelled", waiting=waiting, events=events)
                )
                await waiting.wait()
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            assert task.cancelled(), "caller cancellation did not propagate"
            assert asyncio.all_tasks() == before, "guide tasks survived"
            return outcomes, tuple(events)
    finally:
        del sys.modules[name]


if __name__ == "__main__":
    validate(asyncio.run(run_guide(Path(sys.argv[1]))))
    print("DIRECT_STREAMING_GUIDE_ARTIFACT_OK")
