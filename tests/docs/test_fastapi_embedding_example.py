"""The embedding tutorial preserves host authority and runtime ownership."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
from examples import fastapi_embedding as example

from agnara import App
from agnara.execution import CapabilityRuntime, ExecutionContext


def test_embedding_requests_isolate_contexts_and_deny_before_handler(monkeypatch) -> None:
    effects: list[str] = []
    contexts: list[ExecutionContext] = []
    closed: list[CapabilityRuntime] = []
    loops: list[asyncio.AbstractEventLoop] = []
    original_invoke = CapabilityRuntime.invoke_result
    original_close = CapabilityRuntime.aclose

    def application() -> App:
        app = App("orders")

        @app.capability(scopes={"orders:read"}, output=dict[str, str])
        def summary(order_id: str) -> dict[str, str]:
            effects.append(order_id)
            return {"order": order_id, "status": "shipped"}

        return app

    async def invoke(self, context):
        contexts.append(context)
        loops.append(asyncio.get_running_loop())
        # Yield with each context live so the concurrent requests overlap.
        await asyncio.sleep(0)
        return await original_invoke(self, context)

    async def close(self):
        loops.append(asyncio.get_running_loop())
        await original_close(self)
        closed.append(self)

    monkeypatch.setattr(example, "build_application", application)
    monkeypatch.setattr(CapabilityRuntime, "invoke_result", invoke)
    monkeypatch.setattr(CapabilityRuntime, "aclose", close)

    async def run() -> None:
        before = asyncio.all_tasks()
        host = example.build_host()
        async with host.router.lifespan_context(host):
            for credential in (None, "Bearer unknown"):
                headers = {} if credential is None else {"authorization": credential}
                status, body = await example.drive(host, "/orders/A-1", headers)
                assert (status, json.loads(body)) == (401, {"detail": "unauthenticated"})
            assert not contexts and not effects
            status, body = await example.drive(host, "/health", {})
            assert (status, json.loads(body)) == (200, {"status": "ok"})
            assert not contexts

            async with asyncio.TaskGroup() as group:
                allowed = group.create_task(
                    example.drive(
                        host,
                        "/orders/A-1",
                        {"authorization": "Bearer token-alice", "x-request-id": "alice-1"},
                    )
                )
                denied = group.create_task(
                    example.drive(
                        host,
                        "/orders/B-2",
                        {"authorization": "Bearer token-bob", "x-request-id": "bob-2"},
                    )
                )
                malformed = group.create_task(
                    example.drive(
                        host,
                        "/orders/C-3",
                        {"authorization": "Bearer token-alice", "x-request-id": "x" * 129},
                    )
                )
            for task, expected in (
                (allowed, (200, {"order": "A-1", "status": "shipped"})),
                (denied, (403, {"error": "forbidden"})),
                (malformed, (200, {"order": "C-3", "status": "shipped"})),
            ):
                status, body = task.result()
                assert (status, json.loads(body)) == expected
            assert sorted(effects) == ["A-1", "C-3"]
            assert not closed
        assert len(closed) == 1
        assert all(loop is asyncio.get_running_loop() for loop in loops)
        assert asyncio.all_tasks() == before

    asyncio.run(run())
    assert len(contexts) == len({id(context) for context in contexts}) == 3
    assert len({context.execution_id for context in contexts}) == 3
    by_order = {context.invocation.payload["order_id"]: context for context in contexts}
    assert by_order["A-1"].principal.identity == "alice"
    assert by_order["B-2"].principal.identity == "bob"
    assert [by_order[key].tracking_id for key in ("A-1", "B-2", "C-3")] == [
        "alice-1",
        "bob-2",
        None,
    ]
    assert all(not context.invocation.metadata for context in contexts)


def test_embedding_exceptional_lifespan_closes_runtime(monkeypatch) -> None:
    closed: list[CapabilityRuntime] = []
    original_close = CapabilityRuntime.aclose

    async def run() -> None:
        owner = asyncio.get_running_loop()

        async def close(self):
            assert asyncio.get_running_loop() is owner
            await original_close(self)
            closed.append(self)

        monkeypatch.setattr(CapabilityRuntime, "aclose", close)
        host = example.build_host()
        with pytest.raises(RuntimeError, match="host exit"):
            async with host.router.lifespan_context(host):
                assert (await example.drive(host, "/health", {}))[0] == 200
                raise RuntimeError("host exit")
        assert len(closed) == 1

    asyncio.run(run())


@pytest.mark.parametrize("label", ["", "a" * 129, "req\r\nx-injected: 1", "has space", "é"])
def test_embedding_rejects_unbounded_or_non_token_correlation(label: str) -> None:
    assert example.correlate(label) is None


def test_embedding_script_runs() -> None:
    completed = subprocess.run(
        [sys.executable, "examples/fastapi_embedding.py"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert '200 {"order":"A-1","status":"shipped"}' in completed.stdout
    assert '403 {"error":"forbidden"}' in completed.stdout
    assert completed.stdout.count('401 {"detail":"unauthenticated"}') == 2
