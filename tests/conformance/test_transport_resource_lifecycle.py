"""One owned-resource contract through direct calls, HTTP and the official MCP client."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest
from mcp_types import TextContent

from agnara import Agnara
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    Success,
    invoke_result,
)
from agnara_http import Binding, BindingSource, Http
from agnara_mcp import Mcp, McpAuthorization, build_mcp_server
from mcp import Client

SECRET = "private-resource-contract-diagnostic"
SURFACES = ("direct", "http", "mcp")


@dataclass
class _Resource:
    serial: int
    loop: asyncio.AbstractEventLoop
    closed: bool = False


@dataclass
class _Outcome:
    code: str
    value: Any
    wire: str


class _Scenario:
    def __init__(self, mode: str):
        self.events: list[tuple[str, int]] = []
        self.resources: list[_Resource] = []
        self.by_value: dict[int, _Resource] = {}
        self.started = {value: asyncio.Event() for value in (1, 2)}
        self.release = {value: asyncio.Event() for value in (1, 2)}
        self.closed = asyncio.Event()

        @provider(scope=Scope.INVOCATION)
        async def acquire() -> AsyncIterator[_Resource]:
            resource = _Resource(len(self.resources) + 1, asyncio.get_running_loop())
            self.resources.append(resource)
            self.events.append(("open", resource.serial))
            try:
                yield resource
            finally:
                assert resource.loop is asyncio.get_running_loop()
                assert not resource.closed
                resource.closed = True
                self.events.append(("close", resource.serial))
                self.closed.set()

        self.app = Agnara("lifecycle")

        @self.app.capability(
            output=int, scopes=("lifecycle:run",) if mode.startswith("denied") else ()
        )
        async def execute(value: int, resource: _Resource) -> Any:
            assert not resource.closed and resource.loop is asyncio.get_running_loop()
            self.by_value[value] = resource
            self.events.append(("enter", resource.serial))
            self.started[value].set()
            try:
                if mode in {"cancel", "concurrent"}:
                    await self.release[value].wait()
                if mode == "handler_failure":
                    raise RuntimeError(SECRET)
                if mode == "output_failure":
                    return SECRET
                return value * 2
            finally:
                self.events.append(("exit", resource.serial))

        self.execute = execute
        self.dependencies = DIRegistry()
        self.dependencies.bind(_Resource, acquire)
        self.capabilities = self.app.compile()
        self.plan = ExecutionPlan.compile(self.capabilities["lifecycle.execute"], self.dependencies)

    def assert_closed(self, count: int) -> None:
        assert len(self.resources) == count
        for resource in self.resources:
            assert resource.closed
            for event in ("open", "enter", "exit", "close"):
                assert self.events.count((event, resource.serial)) == 1


@asynccontextmanager
async def _http_lifespan(application):
    incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    outgoing: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    async with asyncio.TaskGroup() as owned:
        owned.create_task(application({"type": "lifespan"}, incoming.get, outgoing.put))
        await incoming.put({"type": "lifespan.startup"})
        assert (await outgoing.get())["type"] == "lifespan.startup.complete"
        try:
            yield
        finally:
            await incoming.put({"type": "lifespan.shutdown"})
            assert (await outgoing.get())["type"] == "lifespan.shutdown.complete"


async def _http_call(application, value) -> _Outcome:
    messages = []
    incoming = [{"type": "http.request", "body": json.dumps(value).encode(), "more_body": False}]

    async def receive():
        return incoming.pop(0)

    async def send(message):
        messages.append(message)

    await application(
        {
            "type": "http",
            "method": "POST",
            "path": "/invoke",
            "raw_path": b"/invoke",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "root_path": "",
        },
        receive,
        send,
    )
    wire = b"".join(message.get("body", b"") for message in messages[1:]).decode()
    payload = json.loads(wire)
    status = messages[0]["status"]
    if status == 200:
        return _Outcome("ok", payload, wire)
    assert (
        status == {"invalid_input": 400, "forbidden": 403, "internal_failure": 500}[payload["code"]]
    )
    return _Outcome(payload["code"], None, wire)


def _reject_authenticated(_identity):
    raise ValueError("this public conformance fixture has no authenticated mapping")


@asynccontextmanager
async def _surface(surface: str, mode: str):
    scenario = _Scenario(mode)
    async with asyncio.timeout(5):
        if surface == "http":
            http = Http("public")
            http.post("/invoke", scenario.execute, Binding("value", BindingSource.BODY))
            application = http.compile(scenario.capabilities, dependencies=scenario.dependencies)

            async def call(value):
                return await _http_call(application, value)

            async with _http_lifespan(application):
                yield scenario, call
            return

        container = DIContainer(scenario.dependencies)
        try:
            if surface == "direct":

                async def direct_call(value):
                    result = await invoke_result(
                        scenario.plan,
                        ExecutionContext(
                            Invocation(scenario.plan.definition.id, {"value": value}, {}), container
                        ),
                    )
                    if isinstance(result, Success):
                        return _Outcome("ok", result.value, repr(result))
                    assert isinstance(result, Failure)
                    return _Outcome(result.code.value, None, repr(result))

                yield scenario, direct_call
                return

            assert surface == "mcp"
            mcp = Mcp(scenario.app)
            mcp.tool(scenario.execute)
            exposures = mcp.compile()
            server = build_mcp_server(
                exposures,
                [scenario.plan],
                container,
                authorization=McpAuthorization(exposures, _reject_authenticated),
                name="resource-lifecycle-conformance",
                version="fixture",
            )
            async with Client(server, mode="auto") as client:

                async def mcp_call(value):
                    result = await client.call_tool("lifecycle.execute", {"value": value})
                    assert len(result.content) == 1 and isinstance(result.content[0], TextContent)
                    payload = json.loads(result.content[0].text)
                    wire = result.model_dump_json()
                    if result.is_error:
                        return _Outcome(payload["code"], None, wire)
                    assert result.structured_content == payload
                    return _Outcome("ok", payload["result"], wire)

                yield scenario, mcp_call
        finally:
            await container.aclose()


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("success", "ok"),
        ("invalid", "invalid_input"),
        ("denied", "forbidden"),
        ("denied_bad", "forbidden"),
        ("handler_failure", "internal_failure"),
        ("output_failure", "internal_failure"),
    ],
)
def test_result_ordering_redaction_and_cleanup_match_across_surfaces(surface, mode, expected):
    async def run():
        async with _surface(surface, mode) as (scenario, call):
            outcome = await call("bad" if mode in {"invalid", "denied_bad"} else 1)
            assert outcome.code == expected
            assert SECRET not in outcome.wire
            if expected == "ok":
                assert outcome.value == 2
            if mode in {"invalid", "denied", "denied_bad"}:
                assert scenario.resources == [] and scenario.events == []
            else:
                scenario.assert_closed(1)
                assert scenario.events == [("open", 1), ("enter", 1), ("exit", 1), ("close", 1)]
        scenario.assert_closed(0 if mode in {"invalid", "denied", "denied_bad"} else 1)
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())


@pytest.mark.parametrize("surface", SURFACES)
def test_caller_cancellation_closes_entered_resource_and_joins_owned_tasks(surface):
    async def run():
        async with _surface(surface, "cancel") as (scenario, call):
            async with asyncio.TaskGroup() as owned:
                task = owned.create_task(call(1))
                await scenario.started[1].wait()
                assert not scenario.resources[0].closed
                task.cancel()
            assert task.cancelled()
            await scenario.closed.wait()
            scenario.assert_closed(1)
        scenario.assert_closed(1)
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())


@pytest.mark.parametrize("surface", SURFACES)
def test_concurrent_calls_keep_resources_isolated_until_their_own_exit(surface):
    async def run():
        async with _surface(surface, "concurrent") as (scenario, call):
            async with asyncio.TaskGroup() as owned:
                first = owned.create_task(call(1))
                second = owned.create_task(call(2))
                await scenario.started[1].wait()
                await scenario.started[2].wait()
                one, two = scenario.by_value[1], scenario.by_value[2]
                assert one is not two and not one.closed and not two.closed
                scenario.release[1].set()
                assert (await first).value == 2
                assert one.closed and not two.closed
                assert ("close", two.serial) not in scenario.events
                scenario.release[2].set()
                assert (await second).value == 4
            scenario.assert_closed(2)
        scenario.assert_closed(2)
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())
