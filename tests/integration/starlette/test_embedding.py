"""Starlette clean-room, embedded and side-by-side conformance evidence."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Awaitable, Callable, MutableMapping
from pathlib import Path
from typing import Any

from tests.integration.starlette.reference_application import FixtureState, create_application

type Message = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[Message]]


async def _request(
    app: Any,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Exercise Starlette's ASGI boundary without its deprecated TestClient alias."""

    received = False
    sent: list[Message] = []

    async def receive() -> Message:
        nonlocal received
        if received:
            raise AssertionError("request consumed more than one body event")
        received = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (name.encode("latin-1"), value.encode("latin-1"))
                for name, value in (headers or {}).items()
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    body = b"".join(message.get("body", b"") for message in sent)
    return sent[0]["status"], json.loads(body)


def test_native_and_embedded_routes_share_one_lifespan_and_runtime() -> None:
    async def run() -> None:
        state = FixtureState()
        app = create_application(state)
        async with app.router.lifespan_context(app):
            assert await _request(app, "GET", "/native") == (200, {"native": "starlette"})
            assert await _request(
                app, "GET", "/agnara/echo/hello", headers={"x-fixture-auth": "reader"}
            ) == (200, {"ok": True, "value": "agnara:hello"})
            assert await _request(
                app, "GET", "/agnara/compose", headers={"x-fixture-auth": "reader"}
            ) == (200, {"ok": True, "value": "composed:agnara:child"})
            assert await _request(app, "GET", "/agnara/echo/no-auth") == (
                403,
                {"ok": False, "code": "forbidden"},
            )

        assert (state.starts, state.stops) == (1, 1)

    asyncio.run(run())


def test_duplicate_idempotency_failure_and_stream_refusal_have_canonical_outcomes() -> None:
    async def run() -> None:
        state = FixtureState()
        app = create_application(state)
        headers = {"x-fixture-auth": "reader", "x-fixture-retry": "fixture-duplicate"}
        async with app.router.lifespan_context(app):
            assert await _request(app, "POST", "/agnara/write", headers=headers) == (
                200,
                {"ok": True, "value": 1},
            )
            assert await _request(app, "POST", "/agnara/write", headers=headers) == (
                200,
                {"ok": True, "value": 1},
            )
            assert state.effects == 1

            assert await _request(
                app, "GET", "/agnara/failure", headers={"x-fixture-auth": "reader"}
            ) == (400, {"ok": False, "code": "internal_failure"})
            assert await _request(
                app, "GET", "/agnara/stream", headers={"x-fixture-auth": "reader"}
            ) == (400, {"ok": False, "code": "internal_failure"})

    asyncio.run(run())


def test_disconnect_cancels_structured_runtime_work_and_closes_it() -> None:
    async def run() -> None:
        state = FixtureState()
        app = create_application(state)
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/agnara/disconnect",
            "raw_path": b"/agnara/disconnect",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"x-fixture-auth", b"reader")],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
        messages = iter(
            (
                {"type": "http.request", "body": b"", "more_body": False},
                {"type": "http.disconnect"},
            )
        )
        sent: list[Message] = []

        async def receive() -> Message:
            return next(messages)

        async def send(message: Message) -> None:
            sent.append(message)

        async with app.router.lifespan_context(app):
            await app(scope, receive, send)
            assert state.cancellations == 1
            assert sent[0]["status"] == 499

        assert (state.starts, state.stops) == (1, 1)

    asyncio.run(run())


def test_clean_room_installs_wheels_without_workspace_source_discovery(tmp_path: Path) -> None:
    """The fixture imports installed artifacts from an isolated Python process."""

    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    workspace = Path(__file__).parents[3]
    build = subprocess.run(
        ["uv", "build", "--all-packages", "--wheel", "--out-dir", str(wheelhouse)],
        check=False,
        cwd=workspace,
        text=True,
        capture_output=True,
    )
    assert build.returncode == 0, build.stderr

    environment = tmp_path / "environment"
    created = subprocess.run(
        ["uv", "venv", "--python", "3.14", str(environment)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert created.returncode == 0, created.stderr
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    core_installed = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "agnara",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert core_installed.returncode == 0, core_installed.stderr
    core_only = subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            "import agnara\nimport sys\nassert 'starlette' not in sys.modules",
        ],
        check=False,
        cwd=tmp_path,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "VIRTUAL_ENV"}
        },
        text=True,
        capture_output=True,
    )
    assert core_only.returncode == 0, core_only.stderr
    installed = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "agnara-http",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert installed.returncode == 0, installed.stderr
    starlette = subprocess.run(
        ["uv", "pip", "install", "--python", str(python), "starlette==1.6.0"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert starlette.returncode == 0, starlette.stderr
    script = """
import asyncio
from contextlib import asynccontextmanager
from agnara import Agnara
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

app = Agnara('cleanroom')
@app.capability
def ping() -> str:
    return 'pong'

capabilities = app.compile()
registry = DIRegistry()
container = DIContainer(registry)
plan = ExecutionPlan.compile(capabilities['cleanroom.ping'], registry)
runtime = CapabilityRuntime(capabilities, [plan], container)

@asynccontextmanager
async def lifespan(_: Starlette):
    try:
        yield
    finally:
        await runtime.aclose()

async def endpoint(_: Request):
    context = ExecutionContext(
        Invocation(capabilities['cleanroom.ping'].id, {}, {}),
        container,
    )
    result = await runtime.invoke_result(context)
    assert isinstance(result, Success)
    return JSONResponse({'value': result.value})

host = Starlette(routes=[Route('/ping', endpoint)], lifespan=lifespan)
async def run():
    sent = []
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    async def send(message):
        sent.append(message)
    async with host.router.lifespan_context(host):
        scope = {
            'type': 'http',
            'asgi': {'version': '3.0'},
            'http_version': '1.1',
            'method': 'GET',
            'scheme': 'http',
            'path': '/ping',
            'raw_path': b'/ping',
            'query_string': b'',
            'root_path': '',
            'headers': [],
            'client': ('127.0.0.1', 1),
            'server': ('test', 80),
        }
        await host(scope, receive, send)
    assert sent[0]['status'] == 200
asyncio.run(run())
print('clean-room-ok')
"""
    isolated = subprocess.run(
        [str(python), "-I", "-c", script],
        check=False,
        cwd=tmp_path,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "VIRTUAL_ENV"}
        },
        text=True,
        capture_output=True,
    )
    assert isolated.returncode == 0, isolated.stderr
    assert isolated.stdout.strip() == "clean-room-ok"
