"""The installed-wheel consumer must actually own its mounted child's lifespan."""

from __future__ import annotations

import asyncio

import pytest

from agnara.di import DIContainer
from tests.reference_apps import side_by_side_fastapi as example


def assert_closed(state: example.State) -> None:
    assert state.child is None
    assert (state.starts, state.stops) == (1, 1)
    assert len(state.resources) == 1 and state.resources[0].closed
    assert len({loop for _, loop in state.events}) == 1
    assert [name for name, _ in state.events][-3:] == [
        "resource.close",
        "child.stop",
        "host.stop",
    ]


def test_installed_consumer_main_exercises_real_cancellation(monkeypatch, capsys) -> None:
    states = []
    cancelled = []
    original_host = example.build_host
    original_read = example.Resource.read

    def build_host(state):
        states.append(state)
        return original_host(state)

    async def read(self, value):
        try:
            return await original_read(self, value)
        except asyncio.CancelledError:
            assert not self.closed, "resource closed before its caller drained"
            cancelled.append(self)
            raise

    monkeypatch.setattr(example, "build_host", build_host)
    monkeypatch.setattr(example.Resource, "read", read)

    async def run() -> None:
        before = asyncio.all_tasks()
        await example.main()
        assert len(states) == 3
        assert cancelled == [states[-1].resources[0]]
        for state in states:
            assert_closed(state)
        assert asyncio.all_tasks() == before

    asyncio.run(run())
    assert capsys.readouterr().out.splitlines() == ["SIDE_BY_SIDE_DOGFOOD_OK"]


@pytest.mark.parametrize("when", ["before_join", "on_completion"])
def test_consumer_owner_cancellation_drains_and_closes_host(monkeypatch, capsys, when) -> None:
    states = []
    original_host = example.build_host

    def build_host(state):
        states.append(state)
        return original_host(state)

    monkeypatch.setattr(example, "build_host", build_host)

    async def run() -> None:
        before = asyncio.all_tasks()
        owner = asyncio.current_task()
        assert owner is not None
        loop = asyncio.get_running_loop()
        original_create = loop.create_task
        children = []
        cancellation_requests = []

        def cancel_owner() -> None:
            cancellation_requests.append(owner.cancel())

        def create_child(coro, **kwargs):
            task = original_create(coro, **kwargs)
            # Lifespan tasks retain their ordinary scheduling; target only
            # the real blocked HTTP request that main owns for cancellation.
            if coro.cr_code is example.request.__code__:
                children.append(task)
                if when == "on_completion":
                    task.add_done_callback(lambda _: cancel_owner())
                else:
                    loop.call_soon(cancel_owner)
            return task

        with monkeypatch.context() as patch:
            patch.setattr(loop, "create_task", create_child)
            with pytest.raises(asyncio.CancelledError):
                await example.main()
        assert cancellation_requests == [True]
        assert len(children) == 1 and children[0].cancelled()
        assert len(states) == 3
        assert states[-1].resources[0].finished.is_set()
        for state in states:
            assert_closed(state)
        assert asyncio.all_tasks() == before

    asyncio.run(run())
    assert "SIDE_BY_SIDE_DOGFOOD_OK" not in capsys.readouterr().out


@pytest.mark.parametrize("exceptional", [False, True])
def test_host_owns_child_container_and_resources_on_one_loop(monkeypatch, exceptional) -> None:
    loops: list[int] = []
    original = DIContainer.__init__

    def construct(self, registry):
        loops.append(id(asyncio.get_running_loop()))
        original(self, registry)

    monkeypatch.setattr(DIContainer, "__init__", construct)
    state = example.State()
    host = example.build_host(state)
    assert loops == [] and state.child is None

    async def run() -> None:
        before = asyncio.all_tasks()

        async def invoke() -> None:
            async with host.router.lifespan_context(host):
                assert await example.request(host, "/native") == (200, {"native": "fastapi"})
                assert state.resources == []
                assert [name for name, _ in state.events] == [
                    "host.start",
                    "child.compile",
                    "child.start",
                ]
                for value in ("first", "second"):
                    assert await example.request(host, f"/agnara/check/{value}") == (
                        200,
                        {"agnara": value},
                    )
                assert len(state.resources) == 1 and not state.resources[0].closed
                if exceptional:
                    raise RuntimeError("owner failure")

        if exceptional:
            with pytest.RaisesGroup(pytest.RaisesExc(RuntimeError, match="owner failure")):
                await invoke()
        else:
            await invoke()
        assert_closed(state)
        assert asyncio.all_tasks() == before
        assert len(loops) == 1 and {loop for _, loop in state.events} == set(loops)

    asyncio.run(run())


def test_cancelled_http_call_drains_before_child_shutdown(monkeypatch) -> None:
    async def run() -> None:
        before = asyncio.all_tasks()
        started = asyncio.Event()
        finished = asyncio.Event()

        async def read(self, value):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                finished.set()

        monkeypatch.setattr(example.Resource, "read", read)
        state = example.State()
        host = example.build_host(state)
        async with host.router.lifespan_context(host):
            async with asyncio.TaskGroup() as tasks:
                call = tasks.create_task(example.request(host, "/agnara/check/wait"))
                async with asyncio.timeout(5):
                    await started.wait()
                call.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await call
            assert finished.is_set()
            assert not state.resources[0].closed
            assert "child.stop" not in [name for name, _ in state.events]
        assert_closed(state)
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_handler_failure_keeps_diagnostics_private_and_closes_resource(monkeypatch) -> None:
    async def read(self, value):
        raise RuntimeError("private resource diagnostic")

    monkeypatch.setattr(example.Resource, "read", read)

    async def run() -> None:
        state = example.State()
        host = example.build_host(state)
        async with host.router.lifespan_context(host):
            status, body = await example.request(host, "/agnara/check/failure")
            assert status == 500 and "private" not in str(body)
            assert not state.resources[0].closed
        assert_closed(state)

    asyncio.run(run())


@pytest.mark.parametrize("stage", ["startup", "shutdown"])
def test_child_handshake_refusal_propagates_and_drains(stage) -> None:
    async def run() -> None:
        before = asyncio.all_tasks()
        closed = False

        async def child(scope, receive, send):
            nonlocal closed
            try:
                assert (await receive())["type"] == "lifespan.startup"
                if stage == "shutdown":
                    await send({"type": "lifespan.startup.complete"})
                    assert (await receive())["type"] == "lifespan.shutdown"
                await send({"type": f"lifespan.{stage}.failed", "message": "private"})
                await asyncio.Event().wait()
            finally:
                closed = True

        with pytest.RaisesGroup(pytest.RaisesExc(RuntimeError, match=f"child {stage} failed")):
            async with example.child_lifespan(child):
                assert stage == "shutdown"
        assert closed
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_silent_child_startup_is_bounded_and_cancelled() -> None:
    async def run() -> None:
        before = asyncio.all_tasks()
        closed = False

        async def child(scope, receive, send):
            nonlocal closed
            try:
                await receive()
                await asyncio.Event().wait()
            finally:
                closed = True

        with pytest.RaisesGroup(TimeoutError):
            async with example.child_lifespan(child, timeout=0.02):
                pytest.fail("silent startup must not yield control to the host")
        assert closed
        assert asyncio.all_tasks() == before

    asyncio.run(run())
