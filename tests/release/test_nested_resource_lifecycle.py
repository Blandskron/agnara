"""Run the same public consumer used by the installed candidate-wheel lane."""

import asyncio

import pytest

from agnara.di import DIContainer
from tests.reference_apps.nested_resource_lifecycle import CASES, Case, run_case


@pytest.mark.parametrize("case", CASES)
def test_nested_resource_lifecycle(case: Case) -> None:
    asyncio.run(run_case(case))


def test_nested_consumer_preserves_owner_cancellation_and_closes_singleton(monkeypatch) -> None:
    original_create = asyncio.TaskGroup.create_task
    original_close = DIContainer.aclose
    closed = []

    def cancel_owner(self, coro, **kwargs):
        owner = asyncio.current_task()
        assert owner is not None
        task = original_create(self, coro, **kwargs)
        # Deliver owner cancellation when the deliberately cancelled child
        # finishes, before the consumer resumes its await.
        task.add_done_callback(lambda _: owner.cancel())
        return task

    async def record_close(self):
        shared = list(self.singleton_cache.values())
        assert len(shared) == 1 and not shared[0].closed
        await original_close(self)
        assert shared[0].closed and not self.singleton_cache
        closed.extend(shared)

    monkeypatch.setattr(asyncio.TaskGroup, "create_task", cancel_owner)
    monkeypatch.setattr(DIContainer, "aclose", record_close)

    async def run() -> None:
        before = asyncio.all_tasks()
        with pytest.raises(asyncio.CancelledError):
            await run_case("cancelled")
        assert len(closed) == 1
        assert asyncio.all_tasks() == before

    asyncio.run(run())
