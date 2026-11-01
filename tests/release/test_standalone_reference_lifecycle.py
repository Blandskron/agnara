"""Standalone candidate consumer owns stream work and preserves cancellation."""

import asyncio

import pytest

from agnara.execution import CapabilityRuntime
from tests.reference_apps.standalone import main


def test_standalone_reference_completes_without_surviving_tasks(capsys) -> None:
    async def run() -> None:
        before = asyncio.all_tasks()
        await main()
        assert asyncio.all_tasks() == before

    asyncio.run(run())
    assert capsys.readouterr().out.splitlines() == ["STANDALONE_DOGFOOD_OK"]


@pytest.mark.parametrize("when", ["before_join", "on_completion"])
def test_standalone_owner_cancellation_joins_stream_before_shutdown(
    monkeypatch, capsys, when
) -> None:
    original_close = CapabilityRuntime.aclose
    children: list[asyncio.Task] = []
    closed: list[CapabilityRuntime] = []
    cancellation_requests: list[bool] = []

    async def record_close(self: CapabilityRuntime) -> None:
        assert children and all(task.done() for task in children)
        await original_close(self)
        closed.append(self)

    monkeypatch.setattr(CapabilityRuntime, "aclose", record_close)

    async def run() -> None:
        before = asyncio.all_tasks()
        owner = asyncio.current_task()
        assert owner is not None
        loop = asyncio.get_running_loop()
        original_create = loop.create_task

        def request_cancellation() -> None:
            cancellation_requests.append(owner.cancel())

        def create_child(coro, **kwargs):
            task = original_create(coro, **kwargs)
            children.append(task)
            if when == "on_completion":
                task.add_done_callback(lambda _: request_cancellation())
            else:
                # The child was scheduled first; cancel its owner on the
                # next loop turn, before the owner can join it.
                loop.call_soon(request_cancellation)
            return task

        # Observe the event-loop creation boundary so this regression covers
        # both the original bare task and the corrected task-group ownership.
        with monkeypatch.context() as patch:
            patch.setattr(loop, "create_task", create_child)
            with pytest.raises(asyncio.CancelledError):
                await main()
        assert cancellation_requests == [True]
        assert len(children) == len(closed) == 1
        assert children[0].cancelled()
        assert asyncio.all_tasks() == before

    asyncio.run(run())
    assert "STANDALONE_DOGFOOD_OK" not in capsys.readouterr().out
