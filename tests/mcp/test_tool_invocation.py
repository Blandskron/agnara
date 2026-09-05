"""E7.8b: the tools/call dispatcher, its lifecycle and its authorization guard.

These tests drive the dispatcher directly so one behaviour fails in one place.
The official-client evidence for the same surface lives in
``test_sdk_conformance.py``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass
from typing import Any, cast

import pytest
from mcp.server import ServerRequestContext
from mcp_types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    InputRequiredResult,
    TaskMetadata,
    TextContent,
)

from agnara import Agnara, CapabilityId, Confirmation
from agnara.core.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation
from agnara.policy import (
    ConfirmationEvidence,
    ConfirmationVerdict,
    InteractionKind,
    Principal,
)
from agnara_mcp import (
    Mcp,
    McpAuthenticatedIdentity,
    McpAuthorization,
    McpInvocationDefinitionError,
    McpToolInvoker,
)
from mcp import MCPError


def run[T](awaitable: Awaitable[T]) -> T:
    async def bounded() -> T:
        async with asyncio.timeout(10):
            return await awaitable

    return asyncio.run(bounded())


def params(name: str, arguments: dict[str, Any] | None = None) -> CallToolRequestParams:
    return CallToolRequestParams(name=name, arguments=arguments)


@dataclass
class FakeContext:
    """A request context carrying only the field the dispatcher may read.

    Anything else the dispatcher reached for would raise here instead of
    silently coupling the adapter to the SDK's per-request object.
    """

    request_id: object = 1


def request_context(request_id: object = 1) -> ServerRequestContext[Any]:
    """Hand the dispatcher a context shaped like the one the SDK builds."""
    return cast("ServerRequestContext[Any]", FakeContext(request_id))


def payload(result: CallToolResult | InputRequiredResult) -> Any:
    assert isinstance(result, CallToolResult)
    assert len(result.content) == 1
    block = result.content[0]
    assert isinstance(block, TextContent)
    return json.loads(block.text)


def completed(result: CallToolResult | InputRequiredResult) -> CallToolResult:
    assert isinstance(result, CallToolResult)
    return result


class Ledger:
    """A resource whose open/close order proves the invocation scope ran."""

    name = "ledger"


class Journal:
    """Records what a capability actually did, so absence of effect is testable."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.closed: list[str] = []


@dataclass
class _TelemetryJournal:
    """What an observer saw, reduced to the fields this boundary owns."""

    starts: list[tuple[str, str | None]]
    terminals: list[tuple[str, str | None, str]]

    def on_invocation_start(self, event: Any) -> None:
        self.starts.append((str(event.capability_id), event.tracking_id))

    def on_invocation_terminal(self, event: Any) -> None:
        self.terminals.append((str(event.capability_id), event.tracking_id, event.outcome))


@pytest.fixture
def telemetry() -> _TelemetryJournal:
    return _TelemetryJournal(starts=[], terminals=[])


def _observed_surface(hook: _TelemetryJournal) -> McpToolInvoker:
    """The same surface, with plans compiled against a telemetry observer."""
    invoker, _ = surface(hooks=[hook])
    return invoker


def surface(
    *,
    authorized: bool = False,
    timeout: float | None = None,
    hooks: list[Any] | None = None,
) -> tuple[McpToolInvoker, Journal]:
    app = Agnara("dispatch")
    journal = Journal()
    registry = DIRegistry()

    @provider(scope=Scope.INVOCATION)
    async def ledger() -> AsyncIterator[Ledger]:
        journal.calls.append("ledger:open")
        try:
            yield Ledger()
        finally:
            journal.closed.append("ledger")

    registry.bind(Ledger, ledger)

    @app.capability(description="Add two integers.")
    def add(left: int, right: int = 1) -> int:
        journal.calls.append("add")
        return left + right

    @app.capability(scopes={"records:read"})
    def restricted() -> str:
        journal.calls.append("restricted")
        return "private"

    @app.capability
    def with_dependency(label: str, ledger: Ledger) -> str:
        journal.calls.append("with_dependency")
        return f"{label}:{ledger.name}"

    @app.capability
    def with_context(ctx: ExecutionContext) -> dict[str, Any]:
        journal.calls.append("with_context")
        return {
            "principal": ctx.principal.identity,
            "tracking_id": ctx.tracking_id,
            "metadata": dict(ctx.invocation.metadata),
        }

    @app.capability
    def explodes() -> int:
        journal.calls.append("explodes")
        raise RuntimeError("secret internal detail")

    @app.capability
    def unrepresentable() -> object:
        journal.calls.append("unrepresentable")
        return object()

    @app.capability
    async def slow() -> str:
        journal.calls.append("slow:start")
        try:
            await asyncio.sleep(30)
        finally:
            journal.closed.append("slow")
        return "never"

    mcp = Mcp(app)
    for capability in (
        add,
        restricted,
        with_dependency,
        with_context,
        explodes,
        unrepresentable,
        slow,
    ):
        mcp.tool(capability)
    exposures = mcp.compile()
    plans = [
        ExecutionPlan.compile(app.capabilities[key], registry, hooks=hooks or [])
        for key in app.capabilities
    ]

    def identity_to_principal(identity: McpAuthenticatedIdentity) -> Principal:
        return Principal(identity.client_id, scopes=identity.scopes)

    invoker = McpToolInvoker(
        exposures,
        plans,
        DIContainer(registry),
        authorization=McpAuthorization(exposures, identity_to_principal) if authorized else None,
        timeout=timeout,
    )
    return invoker, journal


def call(
    invoker: McpToolInvoker,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    request_id: object = 1,
) -> Any:
    return run(invoker(request_context(request_id), params(name, arguments)))


def test_a_successful_call_returns_the_projected_capability_value() -> None:
    invoker, journal = surface()

    result = call(invoker, "dispatch.add", {"left": 2, "right": 3})

    assert isinstance(result, CallToolResult)
    assert result.is_error is False
    assert result.structured_content == {"result": 5}
    assert payload(result) == {"result": 5}
    assert journal.calls == ["add"]


def test_omitted_arguments_use_compiled_defaults() -> None:
    invoker, _ = surface()

    assert call(invoker, "dispatch.add", {"left": 2}).structured_content == {"result": 3}
    assert call(invoker, "dispatch.add", None).is_error is True


def test_invalid_input_is_a_tool_error_rather_than_a_protocol_error() -> None:
    invoker, journal = surface()

    result = call(invoker, "dispatch.add", {"left": "two", "right": 3})

    assert result.is_error is True
    assert result.structured_content is None
    assert payload(result) == {"code": "invalid_input", "message": "expected int, got str"}
    assert journal.calls == []


def test_an_unknown_tool_is_a_protocol_error_with_no_effect() -> None:
    invoker, journal = surface()

    with pytest.raises(MCPError) as captured:
        call(invoker, "dispatch.absent", {})

    assert captured.value.code == INVALID_PARAMS
    assert captured.value.message == "Unknown tool"
    assert journal.calls == []


def test_task_augmented_and_resumed_calls_are_refused_before_dispatch() -> None:
    invoker, journal = surface()
    ctx = request_context()

    with pytest.raises(MCPError) as task_error:
        run(
            invoker(
                ctx,
                CallToolRequestParams(
                    name="dispatch.add",
                    arguments={"left": 1},
                    task=TaskMetadata(ttl=1000),
                ),
            )
        )
    with pytest.raises(MCPError) as state_error:
        run(
            invoker(
                ctx,
                CallToolRequestParams(
                    name="dispatch.add",
                    arguments={"left": 1},
                    request_state="forged",
                ),
            )
        )

    assert task_error.value.code == state_error.value.code == INVALID_PARAMS
    assert "Task-augmented" in task_error.value.message
    assert "Resuming" in state_error.value.message
    assert journal.calls == []


def test_declared_scopes_deny_an_unauthorized_call_before_any_effect() -> None:
    invoker, journal = surface()

    result = call(invoker, "dispatch.restricted", {})

    assert result.is_error is True
    assert payload(result)["code"] == "forbidden"
    assert journal.calls == []


def test_runtime_owned_parameters_cannot_be_supplied_by_a_caller() -> None:
    invoker, journal = surface()

    dependency = call(invoker, "dispatch.with_dependency", {"label": "x", "ledger": "forged"})
    execution_context = call(invoker, "dispatch.with_context", {"ctx": "forged"})

    for result in (dependency, execution_context):
        assert result.is_error is True
        assert payload(result) == {"code": "invalid_input", "message": "unexpected input"}
    assert journal.calls == []
    assert journal.closed == []


def test_dependencies_resolve_and_close_around_one_invocation() -> None:
    invoker, journal = surface()

    result = call(invoker, "dispatch.with_dependency", {"label": "x"})

    assert result.structured_content == {"result": "x:ledger"}
    assert journal.calls == ["ledger:open", "with_dependency"]
    assert journal.closed == ["ledger"]


def test_execution_context_carries_transport_facts_without_the_protocol_object() -> None:
    invoker, _ = surface()

    observed = call(invoker, "dispatch.with_context", {}, request_id="req-7").structured_content

    assert observed == {
        "result": {
            "principal": "anonymous",
            "tracking_id": "req-7",
            "metadata": {"transport": "mcp", "tool": "dispatch.with_context"},
        }
    }


def test_a_request_id_reaches_telemetry_and_not_only_the_handler(
    telemetry: _TelemetryJournal,
) -> None:
    """Issue #221: the dispatcher sets ``ExecutionContext.tracking_id``.

    Before the fix the runtime built its lifecycle events from invocation
    metadata alone, so this adapter's request id never reached an observer.
    Asserting only that a handler can read ``ctx.tracking_id`` did not catch it.
    """
    invoker = _observed_surface(telemetry)

    call(invoker, "dispatch.with_context", {}, request_id="req-7")

    assert telemetry.starts == [("dispatch.with_context", "req-7")]
    assert telemetry.terminals == [("dispatch.with_context", "req-7", "success")]


@pytest.mark.parametrize("request_id", [None, "x" * 129, ["list"]])
def test_an_unusable_request_id_is_dropped_from_telemetry_too(
    telemetry: _TelemetryJournal,
    request_id: object,
) -> None:
    """The dispatcher already refuses these; telemetry must not resurrect them."""
    invoker = _observed_surface(telemetry)

    call(invoker, "dispatch.with_context", {}, request_id=request_id)

    assert telemetry.starts == [("dispatch.with_context", None)]


@pytest.mark.parametrize("request_id", [None, "x" * 129, ["list"]])
def test_an_unusable_request_id_is_dropped_rather_than_copied(request_id: object) -> None:
    invoker, _ = surface()

    observed = call(invoker, "dispatch.with_context", {}, request_id=request_id)

    assert observed.structured_content["result"]["tracking_id"] is None


def test_a_raising_handler_is_redacted_into_an_internal_failure() -> None:
    invoker, journal = surface()

    result = call(invoker, "dispatch.explodes", {})

    assert result.is_error is True
    assert payload(result) == {
        "code": "internal_failure",
        "message": "capability invocation failed",
    }
    assert "secret internal detail" not in json.dumps(result.model_dump(mode="json"))
    assert journal.calls == ["explodes"]


def test_an_unrepresentable_value_degrades_to_a_tool_error() -> None:
    invoker, journal = surface()

    result = call(invoker, "dispatch.unrepresentable", {})

    assert result.is_error is True
    assert payload(result) == {
        "code": "internal_failure",
        "message": "capability result cannot be represented",
    }
    assert journal.calls == ["unrepresentable"]


def test_a_configured_timeout_becomes_a_canonical_timeout_failure() -> None:
    invoker, journal = surface(timeout=0.05)

    result = call(invoker, "dispatch.slow", {})

    assert result.is_error is True
    assert payload(result)["code"] == "timeout"
    assert journal.calls == ["slow:start"]
    assert journal.closed == ["slow"]


def test_external_cancellation_propagates_instead_of_becoming_a_result() -> None:
    invoker, journal = surface()

    async def scenario() -> None:
        task = asyncio.create_task(invoker(request_context(), params("dispatch.slow", {})))
        while journal.calls != ["slow:start"]:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())
    assert journal.closed == ["slow"]


def test_concurrent_calls_do_not_share_invocation_state() -> None:
    invoker, journal = surface()

    async def scenario() -> list[Any]:
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(
                    invoker(request_context(index), params("dispatch.add", {"left": index}))
                )
                for index in range(8)
            ]
        return [completed(task.result()).structured_content for task in tasks]

    assert run(scenario()) == [{"result": index + 1} for index in range(8)]
    assert journal.calls == ["add"] * 8


def test_authorization_maps_a_verified_identity_into_the_scope_decision() -> None:
    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    invoker, journal = surface(authorized=True)
    token = AccessToken(
        token="opaque",
        client_id="agent-1",
        scopes=["records:read"],
        expires_at=None,
    )
    reset = auth_context_var.set(AuthenticatedUser(token))
    try:
        granted = call(invoker, "dispatch.restricted", {})
    finally:
        auth_context_var.reset(reset)
    denied = call(invoker, "dispatch.restricted", {})

    assert granted.structured_content == {"result": "private"}
    assert denied.is_error is True
    assert payload(denied)["code"] == "forbidden"
    assert journal.calls == ["restricted"]


def test_an_authorization_configured_for_other_exposures_is_refused_at_startup() -> None:
    app = Agnara("mismatch")

    @app.capability
    def first() -> int:
        return 1

    @app.capability
    def second() -> int:
        return 2

    registry = DIRegistry()
    plans = [ExecutionPlan.compile(app.capabilities[key], registry) for key in app.capabilities]
    exposed = Mcp(app)
    exposed.tool(first)
    exposed.tool(second)
    other = Mcp(app)
    other.tool(second)

    with pytest.raises(McpInvocationDefinitionError):
        McpToolInvoker(
            exposed.compile(),
            plans,
            DIContainer(registry),
            authorization=McpAuthorization(other.compile(), lambda identity: Principal("x")),
        )


@pytest.mark.parametrize("timeout", [0, -1, True, "5"])
def test_an_invalid_timeout_is_refused_at_startup(timeout: Any) -> None:
    with pytest.raises(McpInvocationDefinitionError):
        surface(timeout=timeout)


def test_a_confirmation_requirement_reaches_the_interaction_projection() -> None:
    app = Agnara("interactive")
    calls: list[str] = []

    @app.capability(confirmation=Confirmation.REQUIRED)
    def transfer(amount: int) -> str:
        calls.append("transfer")
        return "done"

    class Verifier:
        """Never consulted here: MCP supplies no evidence, so the policy asks first."""

        async def verify(
            self,
            evidence: ConfirmationEvidence,
            *,
            capability_id: CapabilityId,
            invocation: Invocation,
            principal: Principal,
        ) -> ConfirmationVerdict:
            raise AssertionError("verification must not run without evidence")

    registry = DIRegistry()
    mcp = Mcp(app)
    mcp.tool(transfer)
    exposures = mcp.compile()
    plan = ExecutionPlan.compile(
        app.capabilities["interactive.transfer"],
        registry,
        confirmation_verifier=Verifier(),
    )
    invoker = McpToolInvoker(exposures, [plan], DIContainer(registry))

    result = call(invoker, "interactive.transfer", {"amount": 5})

    assert isinstance(result, InputRequiredResult)
    request = result.input_requests["confirmation"]
    assert request.params.requested_schema["required"] == ["confirmed"]
    assert InteractionKind.CONFIRMATION.value == "confirmation"
    assert calls == []


def test_the_invoker_reports_its_frozen_route_table() -> None:
    invoker, _ = surface()

    assert invoker.tool_names[0] == "dispatch.add"
    assert len(invoker.tool_names) == 7
    assert repr(invoker) == "McpToolInvoker(7 tools)"
