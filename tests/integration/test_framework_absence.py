"""Evidence that optional ecosystem frameworks do not infect Agnara distributions."""

from __future__ import annotations

import subprocess
import sys

from tests.architecture.boundaries import (
    CORE_DISTRIBUTION,
    declared_dependencies,
)


def test_core_package_declares_zero_external_dependencies() -> None:
    """The kernel distribution requires only Python >= 3.14."""
    deps = declared_dependencies(CORE_DISTRIBUTION)
    assert deps == [], f"agnara core must have 0 dependencies, got: {deps}"


def test_framework_absence_subprocess_clean_execution() -> None:
    """When optional frameworks are unimportable, core, http, cli and telemetry still work."""
    script = """
import sys

# Block all optional ecosystem frameworks
blocked = [
    "starlette",
    "fastapi",
    "django",
    "litestar",
    "sqlalchemy",
    "pydantic",
    "msgspec",
    "opentelemetry.sdk",
]
for mod in blocked:
    sys.modules[mod] = None

import asyncio
from agnara import Agnara, App, Principal
from agnara.capability import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    CapabilityInvoker,
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
    open_stream,
)
import agnara_http
from agnara_http import Http, HttpApplication
import agnara_cli
import agnara_telemetry

# 1. Kernel compile, dependency injection and execution
project = Agnara("absence_test")
app = App("service")

@app.capability
def echo(msg: str) -> str:
    return f"echo:{msg}"

@app.capability(streaming=True)
async def generate():
    yield "a"
    yield "b"

project.include(app)
caps = project.compile()
registry = DIRegistry()
container = DIContainer(registry)
plans = [ExecutionPlan.compile(caps[cid], registry) for cid in caps]
runtime = CapabilityRuntime(caps, plans, container)

async def run_checks():
    # Invoke complete-result
    ctx = ExecutionContext(
        Invocation(CapabilityId.parse("service.echo"), {"msg": "hello"}, {}),
        container,
    )
    result = await runtime.invoke_result(ctx)
    assert isinstance(result, Success), f"Expected Success, got {result}"
    assert result.value == "echo:hello"

    # Invoke stream
    stream_ctx = ExecutionContext(
        Invocation(CapabilityId.parse("service.generate"), {}, {}),
        container,
    )
    units = []
    async with open_stream(plans[1], stream_ctx) as stream:
        async for unit in stream:
            units.append(unit)
        terminal = stream.terminal
        assert units == ["a", "b"]
        assert terminal == "completed"

    # 2. HTTP ASGI application compilation and execution
    from agnara_http import Binding, BindingSource
    http = Http("test-surface")
    http.get("/echo/{msg}", echo, Binding("msg", BindingSource.PATH))
    asgi = http.compile(caps)

    sent = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        sent.append(message)

    await asgi(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/echo/test",
            "raw_path": b"/echo/test",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 8000),
            "server": ("test", 80),
        },
        receive,
        send,
    )
    assert any(m.get("type") == "http.response.start" and m.get("status") == 200 for m in sent)

    await runtime.aclose()

asyncio.run(run_checks())
print("ABSENCE_TEST_PASSED")
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "ABSENCE_TEST_PASSED" in result.stdout


def test_core_import_does_not_pollute_sys_modules_with_ecosystem_packages() -> None:
    """Importing core must not bring in any forbidden ecosystem dependency."""
    script = """
import sys
import agnara

forbidden = [
    "fastapi", "starlette", "litestar", "django", "flask",
    "sqlalchemy", "pydantic", "msgspec", "opentelemetry.sdk",
]
polluted = [pkg for pkg in forbidden if pkg in sys.modules]
assert not polluted, f"sys.modules contaminated with: {polluted}"
print("NO_POLLUTION")
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "NO_POLLUTION" in result.stdout
