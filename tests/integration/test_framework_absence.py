"""Evidence that optional ecosystem frameworks do not infect Agnara distributions."""

from __future__ import annotations

import subprocess
import sys

from tests.architecture.boundaries import (
    CORE_DISTRIBUTION,
    FORBIDDEN_IN_CORE,
    declared_dependencies,
)


def _run_isolated(script: str, *, blocked: frozenset[str] = frozenset()) -> str:
    prelude = f"import sys\nsys.modules.update(dict.fromkeys({sorted(blocked)!r}))\n"
    result = subprocess.run(
        [sys.executable, "-I", "-c", prelude + script],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return result.stdout


def test_core_package_declares_zero_external_dependencies() -> None:
    """The kernel distribution requires only Python >= 3.14."""
    deps = declared_dependencies(CORE_DISTRIBUTION)
    assert deps == [], f"agnara core must have 0 dependencies, got: {deps}"


def test_framework_absence_subprocess_clean_execution() -> None:
    """When optional frameworks are unimportable, core, http, cli and telemetry still work."""
    script = """
import asyncio
from agnara import Agnara, App, CapabilityId
from agnara.di import DIContainer, DIRegistry
from agnara.execution import (
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    Success,
    open_stream,
)
import agnara_http
from agnara_http import Http
import agnara_cli
import agnara_telemetry

# 1. Kernel compilation and execution (resource DI is exercised separately).
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
    # The telemetry adapter legitimately depends on opentelemetry-api, but
    # importing and using Agnara must not require the application's SDK.
    stdout = _run_isolated(
        script,
        blocked=(FORBIDDEN_IN_CORE - {"opentelemetry"}) | {"opentelemetry.sdk"},
    )
    assert "ABSENCE_TEST_PASSED" in stdout


def test_core_composition_and_resource_cleanup_without_any_ecosystem_package() -> None:
    """A real nested invocation needs neither an adapter nor an optional SDK."""
    script = """
import asyncio
from collections.abc import AsyncIterator

from agnara import Agnara, CapabilityId, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    CapabilityInvoker, CapabilityRuntime, ExecutionContext, ExecutionPlan,
    Failure, FailureCode, Invocation, Success,
)

class Resource:
    pass

async def run_case(scopes, expected, expected_events):
    loop = asyncio.get_running_loop()
    events = []
    app = Agnara("isolated")

    @provider(scope=Scope.INVOCATION)
    async def resource() -> AsyncIterator[Resource]:
        assert asyncio.get_running_loop() is loop
        events.append("resource.open")
        try:
            yield Resource()
        finally:
            assert asyncio.get_running_loop() is loop
            events.append("resource.close")

    @app.capability(scopes=("child:read",), output=str)
    def child(value: str, dependency: Resource) -> str:
        assert isinstance(dependency, Resource)
        events.append("child")
        return f"child:{value}"

    @app.capability(scopes=("parent:read",), output=str)
    async def parent(value: str, invoker: CapabilityInvoker) -> str:
        events.append("parent")
        result = await invoker.invoke(CapabilityId.parse("isolated.child"), {"value": value})
        if isinstance(result, Failure):
            assert result.code is FailureCode.FORBIDDEN
            return "child denied"
        assert isinstance(result, Success)
        return result.value

    registry = DIRegistry()
    registry.bind(Resource, resource)
    capabilities = app.compile()
    plans = [ExecutionPlan.compile(capabilities[key], registry) for key in capabilities]
    container = DIContainer(registry)
    runtime = CapabilityRuntime(capabilities, plans, container)
    try:
        result = await runtime.invoke_result(ExecutionContext(
            Invocation(CapabilityId.parse("isolated.parent"), {"value": "ok"}, {}),
            container,
            principal=Principal("fixture", scopes=scopes),
        ))
        if isinstance(expected, FailureCode):
            assert isinstance(result, Failure), result
            assert result.code is expected, result
        else:
            assert result == expected, result
        # Cleanup must finish before the result is returned, not at shutdown.
        assert events == expected_events, events
    finally:
        await runtime.aclose()
    assert events == expected_events, events

async def main():
    await run_case(
        {"parent:read", "child:read"}, Success("child:ok"),
        ["parent", "resource.open", "child", "resource.close"],
    )
    await run_case({"parent:read"}, Success("child denied"), ["parent"])
    await run_case({"child:read"}, FailureCode.FORBIDDEN, [])

asyncio.run(main())
print("CORE_RESOURCE_ISOLATION_PASSED")
"""
    stdout = _run_isolated(script, blocked=FORBIDDEN_IN_CORE)
    assert "CORE_RESOURCE_ISOLATION_PASSED" in stdout


def test_core_import_does_not_pollute_sys_modules_with_ecosystem_packages() -> None:
    """Importing core must not bring in any forbidden ecosystem dependency."""
    script = f"""
import sys
import agnara

forbidden = {sorted(FORBIDDEN_IN_CORE)!r}
polluted = [
    pkg for pkg in sys.modules
    if any(pkg == root or pkg.startswith(root + ".") for root in forbidden)
]
assert not polluted, f"sys.modules contaminated with: {{polluted}}"
print("NO_POLLUTION")
"""
    assert "NO_POLLUTION" in _run_isolated(script)
