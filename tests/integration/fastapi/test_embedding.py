"""FastAPI clean-room, embedded and side-by-side conformance evidence."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Awaitable, Callable, MutableMapping
from pathlib import Path
from typing import Any

from tests.conformance.harness import HostFixture, HostHarness
from tests.integration.fastapi.reference_application import FixtureState, create_application

type Message = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[Message]]


def _scope(method: str, path: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return {
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
    }


async def _request(
    app: Any,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[bytes, bytes], bytes]:
    """Exercise the real ASGI boundary without TestClient compatibility aliases."""

    received = False
    never = asyncio.Event()
    sent: list[Message] = []

    async def receive() -> Message:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await never.wait()
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        sent.append(message)

    await app(_scope(method, path, headers), receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    response_headers = dict(start["headers"])
    body = b"".join(message.get("body", b"") for message in sent)
    return start["status"], response_headers, body


def _json(response: tuple[int, dict[bytes, bytes], bytes]) -> tuple[int, dict[str, Any]]:
    status, _, body = response
    return status, json.loads(body)


class _FastApiHarnessHost(HostFixture):
    """Adapt the real FastAPI fixture to Task 22's framework-neutral harness."""

    state: FixtureState | None = None

    def call_sync(self, value: object) -> str:
        async def run() -> None:
            state = FixtureState()
            app = create_application(state)
            async with app.router.lifespan_context(app):
                assert _json(
                    await _request(
                        app,
                        "GET",
                        f"/agnara/echo/{value}",
                        headers={"x-fixture-auth": "reader"},
                    )
                ) == (200, {"ok": True, "value": f"agnara:{value}"})
            self.state = state

        asyncio.run(run())
        return super().call_sync(value)

    def stop(self) -> None:
        assert self.state is not None
        assert (self.state.starts, self.state.stops) == (1, 1)
        assert (self.state.projected_starts, self.state.projected_stops) == (1, 1)
        super().stop()


def test_fastapi_fixture_uses_the_framework_neutral_host_harness() -> None:
    host = _FastApiHarnessHost("fastapi")

    result = HostHarness().run_case(
        host,
        "direct-runtime",
        lambda fixture: fixture.call_sync("harness"),
        lambda value: value == "sync:fastapi:harness",
    )

    assert result == "sync:fastapi:harness"
    assert host.events == ["start", "sync", "stop"]


def test_native_direct_and_projected_routes_have_explicit_owners() -> None:
    async def run() -> None:
        state = FixtureState()
        app = create_application(state)
        async with app.router.lifespan_context(app):
            native = await _request(app, "GET", "/native", headers={"x-fixture-auth": "reader"})
            assert _json(native) == (200, {"native": "fastapi", "actor": "fastapi-reader"})
            assert native[1][b"x-fixture-middleware"] == b"active"

            assert _json(
                await _request(
                    app,
                    "GET",
                    "/agnara/echo/hello",
                    headers={"x-fixture-auth": "reader"},
                )
            ) == (200, {"ok": True, "value": "agnara:hello"})
            assert _json(await _request(app, "GET", "/agnara/echo/no-auth")) == (
                403,
                {"ok": False, "code": "forbidden"},
            )
            assert _json(
                await _request(app, "GET", "/agnara/compose", headers={"x-fixture-auth": "reader"})
            ) == (200, {"ok": True, "value": "composed:agnara:child"})

            projected = await _request(app, "GET", "/agnara-http/echo/from-mount")
            assert _json(projected) == (200, "projected:from-mount")
            assert projected[1][b"x-fixture-middleware"] == b"active"

            native_openapi = app.openapi()
            assert "/native" in native_openapi["paths"]
            assert "/agnara-http/echo/{value}" not in native_openapi["paths"]
            assert state.projected is not None
            projected_openapi = state.projected.openapi()
            assert "/echo/{value}" in projected_openapi["paths"]
            assert "/events" not in projected_openapi["paths"]

        assert (state.starts, state.stops) == (1, 1)
        assert (state.projected_starts, state.projected_stops) == (1, 1)

    asyncio.run(run())


def test_host_middleware_and_exception_handler_preserve_canonical_failure() -> None:
    async def run() -> None:
        state = FixtureState()
        app = create_application(state)
        async with app.router.lifespan_context(app):
            native_failure = await _request(app, "GET", "/native/failure")
            assert _json(native_failure) == (418, {"native_error": "handled"})
            assert native_failure[1][b"x-fixture-middleware"] == b"active"

            agnara_failure = await _request(
                app, "GET", "/agnara/failure", headers={"x-fixture-auth": "reader"}
            )
            assert _json(agnara_failure) == (400, {"ok": False, "code": "internal_failure"})
            assert agnara_failure[1][b"x-fixture-middleware"] == b"active"

            stream_refusal = await _request(
                app, "GET", "/agnara/stream", headers={"x-fixture-auth": "reader"}
            )
            assert _json(stream_refusal) == (400, {"ok": False, "code": "internal_failure"})

    asyncio.run(run())


def test_idempotency_and_sse_are_exercised_through_the_fastapi_host() -> None:
    async def run() -> None:
        state = FixtureState()
        app = create_application(state)
        headers = {"x-fixture-auth": "reader", "x-fixture-retry": "fixture-duplicate"}
        async with app.router.lifespan_context(app):
            assert _json(await _request(app, "POST", "/agnara/write", headers=headers)) == (
                200,
                {"ok": True, "value": 1},
            )
            assert _json(await _request(app, "POST", "/agnara/write", headers=headers)) == (
                200,
                {"ok": True, "value": 1},
            )
            assert state.effects == 1

            status, response_headers, body = await _request(app, "GET", "/agnara-http/events")
            assert status == 200
            assert response_headers[b"content-type"] == b"text/event-stream; charset=utf-8"
            assert body == (
                b'data: "one"\n\n'
                b'data: "two"\n\n'
                b"event: agnara.terminal\n"
                b'data: {"outcome":"completed","units":2}\n\n'
            )

    asyncio.run(run())


def test_disconnect_cancels_direct_runtime_work_and_closes_host_owned_resources() -> None:
    async def run() -> None:
        state = FixtureState()
        app = create_application(state)
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
            await app(
                _scope("POST", "/agnara/disconnect", {"x-fixture-auth": "reader"}), receive, send
            )
            assert state.cancellations == 1
            assert sent[0]["status"] == 499

        assert (state.starts, state.stops) == (1, 1)
        assert (state.projected_starts, state.projected_stops) == (1, 1)

    asyncio.run(run())


def test_clean_room_installs_wheels_and_uses_only_public_fastapi_and_agnara_imports(
    tmp_path: Path,
) -> None:
    """The reference application works from installed wheels outside the workspace."""

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
            "import agnara; import sys; assert 'fastapi' not in sys.modules",
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
    fastapi = subprocess.run(
        ["uv", "pip", "install", "--python", str(python), "fastapi==0.141.1"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert fastapi.returncode == 0, fastapi.stderr
    script = """
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from agnara import Agnara
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import CapabilityRuntime, ExecutionContext, ExecutionPlan, Invocation, Success

application = Agnara('cleanroom')
@application.capability
def ping() -> str:
    return 'pong'
capabilities = application.compile()
registry = DIRegistry()
container = DIContainer(registry)
plan = ExecutionPlan.compile(capabilities['cleanroom.ping'], registry)
runtime = CapabilityRuntime(capabilities, [plan], container)

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await runtime.aclose()

host = FastAPI(lifespan=lifespan)
@host.get('/ping')
async def endpoint():
    context = ExecutionContext(
        Invocation(capabilities['cleanroom.ping'].id, {}, {}),
        container,
    )
    result = await runtime.invoke_result(context)
    assert isinstance(result, Success)
    return JSONResponse({'value': result.value})

async def run():
    sent = []
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    async def send(message):
        sent.append(message)
    async with host.router.lifespan_context(host):
        scope = {
            'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
            'method': 'GET', 'scheme': 'http', 'path': '/ping',
            'raw_path': b'/ping', 'query_string': b'', 'root_path': '',
            'headers': [], 'client': ('127.0.0.1', 1), 'server': ('test', 80),
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
