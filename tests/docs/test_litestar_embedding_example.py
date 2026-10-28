"""Exercise the runnable Litestar host's authority, contracts and ownership."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
from examples import litestar_embedding as example

from agnara.di import DIContainer
from agnara.execution import CapabilityRuntime, ExecutionContext, Failure, FailureCode


def assert_closed(state: example.State) -> None:
    assert state.runtime is None and state.container is None
    names = [name for name, _ in state.events]
    assert names[-1] == "runtime.close"
    if "audit.open" in names:
        assert names.count("audit.open") == names.count("audit.close") == 1
        assert names[-2] == "audit.close"
    else:
        assert "audit.close" not in names
    assert len({loop for _, loop in state.events}) == 1


@pytest.mark.parametrize(
    ("credential", "body", "status", "error"),
    [
        (None, b'{"order_id":1}', 401, "unauthenticated"),
        ("Bearer unknown", b'{"order_id":1}', 401, "unauthenticated"),
        ("token-alice", b'{"order_id":1}', 401, "unauthenticated"),
        ("Basic token-alice", b'{"order_id":1}', 401, "unauthenticated"),
        ("Bearer token-bob", b'{"order_id":"bad"}', 403, "forbidden"),
        ("Bearer token-alice", b"{", 400, "malformed_json"),
        ("Bearer token-alice", b"[]", 400, "object_required"),
        ("Bearer token-alice", b"", 400, "object_required"),
        ("Bearer token-alice", b"\xff", 400, "malformed_json"),
        ("Bearer token-alice", b'{"order_id":"bad"}', 422, "invalid_input"),
        ("Bearer token-alice", b"{}", 422, "invalid_input"),
    ],
)
def test_refusal_before_resources_and_handler(credential, body, status, error) -> None:
    async def run() -> None:
        state = example.State()
        host = example.build_host(state)
        async with host.lifespan():
            actual, response = await example.drive(host, body=body, credential=credential)
            assert (actual, json.loads(response)) == (status, {"error": error})
            assert state.audit.orders == []
            assert "audit.open" not in [name for name, _ in state.events]
        assert_closed(state)

    asyncio.run(run())


def test_concurrent_calls_keep_contexts_and_principals_isolated(monkeypatch) -> None:
    contexts: list[ExecutionContext] = []
    original = CapabilityRuntime.invoke_result

    async def invoke(self, context):
        contexts.append(context)
        await asyncio.sleep(0)
        return await original(self, context)

    monkeypatch.setattr(CapabilityRuntime, "invoke_result", invoke)

    async def run() -> None:
        before = asyncio.all_tasks()
        state = example.State()
        host = example.build_host(state)
        async with host.lifespan():
            status, body = await example.drive(host, path="/health", credential=None)
            assert (status, json.loads(body)) == (200, {"status": "ok"})
            assert not contexts and state.audit.orders == []
            async with asyncio.TaskGroup() as tasks:
                first = tasks.create_task(example.drive(host, body=b'{"order_id":1}'))
                second = tasks.create_task(example.drive(host, body=b'{"order_id":2}'))
                denied = tasks.create_task(
                    example.drive(host, body=b'{"order_id":3}', credential="Bearer token-bob")
                )
            assert first.result() == (200, b'{"order_id":1}')
            assert second.result() == (200, b'{"order_id":2}')
            assert denied.result() == (403, b'{"error":"forbidden"}')
            assert sorted(state.audit.orders) == [1, 2]
            assert len(contexts) == len({id(context) for context in contexts}) == 3
            assert len({context.execution_id for context in contexts}) == 3
            by_order = {context.invocation.payload["order_id"]: context for context in contexts}
            assert by_order[1].principal.identity == by_order[2].principal.identity == "alice"
            assert by_order[3].principal.identity == "bob"
            assert all(not context.invocation.metadata for context in contexts)
        assert_closed(state)
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_caller_cancellation_propagates_and_drains_before_shutdown(monkeypatch) -> None:
    async def run() -> None:
        before = asyncio.all_tasks()
        started = asyncio.Event()

        async def record(self, order_id):
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(example.Audit, "record", record)
        state = example.State()
        host = example.build_host(state)
        async with host.lifespan():
            async with asyncio.TaskGroup() as tasks:
                request = tasks.create_task(example.drive(host))
                async with asyncio.timeout(5):
                    await started.wait()
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request
            assert state.audit.orders == []
            assert "runtime.close" not in [name for name, _ in state.events]
        assert_closed(state)
        assert asyncio.all_tasks() == before

    asyncio.run(run())


def test_handler_failure_and_exceptional_host_exit_release_resource(monkeypatch) -> None:
    async def record(self, order_id):
        raise RuntimeError("private handler diagnostic")

    monkeypatch.setattr(example.Audit, "record", record)

    async def run() -> None:
        state = example.State()
        host = example.build_host(state)
        with pytest.RaisesGroup(pytest.RaisesExc(RuntimeError, match="host exit")):
            async with host.lifespan():
                status, body = await example.drive(host)
                assert (status, json.loads(body)) == (500, {"error": "internal_failure"})
                assert b"private" not in body
                raise RuntimeError("host exit")
        assert_closed(state)
        assert state.audit.orders == []

    asyncio.run(run())


def test_runtime_container_is_constructed_and_closed_on_host_loop(monkeypatch) -> None:
    construction_loops: list[int] = []
    close_loops: list[int] = []
    original_init = DIContainer.__init__
    original_close = DIContainer.aclose

    def record_init(self, registry):
        construction_loops.append(id(asyncio.get_running_loop()))
        original_init(self, registry)

    async def record_close(self):
        close_loops.append(id(asyncio.get_running_loop()))
        await original_close(self)

    monkeypatch.setattr(DIContainer, "__init__", record_init)
    monkeypatch.setattr(DIContainer, "aclose", record_close)
    state = example.State()
    host = example.build_host(state)
    assert construction_loops == []
    assert state.runtime is state.container is None

    async def run() -> None:
        async with host.lifespan():
            status, _ = await example.drive(host)
            assert status == 200
        assert_closed(state)

    asyncio.run(run())
    assert len(construction_loops) == len(close_loops) == 1
    assert construction_loops == close_loops
    assert {loop for _, loop in state.events} == set(construction_loops)


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (FailureCode.FORBIDDEN, 403),
        (FailureCode.INVALID_INPUT, 422),
        (FailureCode.TIMEOUT, 504),
        (FailureCode.CONFLICT, 409),
        (FailureCode.INTERNAL_FAILURE, 500),
    ],
)
def test_host_failure_mapping_exposes_only_code(code, status) -> None:
    response = example.failure_response(Failure(code, "private diagnostic", {"secret": "hidden"}))
    assert response.status_code == status
    assert response.content == {"error": str(code)}


def test_script_runs(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "examples/litestar_embedding.py"),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    for line in (
        "success: 200",
        "policy denial: 403",
        "unknown credential: 401",
        "missing credential: 401",
        "malformed JSON: 400",
        "invalid input: 422",
        "native health: 200",
        "recorded orders: [7]",
        "cleanup: ['audit.close', 'runtime.close']",
    ):
        assert line in result.stdout
