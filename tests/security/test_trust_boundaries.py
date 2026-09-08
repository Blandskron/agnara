"""A4-10: what the a4 surface refuses, across HTTP and MCP.

These are authorization and disclosure properties rather than protocol shapes,
so they are written against the public composition API an application actually
uses. Each one names an abuse case from ``docs/THREAT_MODEL.md``: an
unauthenticated caller reaching a scoped capability, a caller supplying its own
authority, confirmation skipped, and server-side detail reaching a client.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from typing import Any, cast

import pytest
from mcp.server import ServerRequestContext
from mcp_types import CallToolRequestParams, CallToolResult, TextContent

from agnara import Agnara, Confirmation, DefinitionError
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    InvocationStartEvent,
    InvocationTerminalEvent,
)
from agnara.policy import Principal, ScopePolicy
from agnara_http import Binding, BindingSource, Http
from agnara_mcp import Mcp, McpToolInvoker

SECRET = "aws-root-key-4c1d9f"


def run[T](awaitable: Awaitable[T]) -> T:
    async def bounded() -> T:
        async with asyncio.timeout(10):
            return await awaitable

    return asyncio.run(bounded())


class Recorder:
    """A telemetry hook that keeps every event the runtime emits."""

    def __init__(self) -> None:
        self.events: list[InvocationStartEvent | InvocationTerminalEvent] = []

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.events.append(event)

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        self.events.append(event)


def call(asgi: Any, method: str, path: str, body: bytes | None = None) -> tuple[int, Any]:
    """Drive one request through a compiled HTTP application."""
    sent: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = [
        {"type": "http.request", "body": body or b"", "more_body": False}
    ]

    async def receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    headers = [(b"content-type", b"application/json")] if body is not None else []
    run(
        asgi(
            {
                "type": "http",
                "method": method,
                "path": path,
                "query_string": b"",
                "root_path": "",
                "headers": headers,
            },
            receive,
            send,
        )
    )
    document = json.loads(sent[1]["body"]) if sent[1]["body"] else None
    return sent[0]["status"], document


def scoped_surface(hooks: tuple[Any, ...] = ()) -> Any:
    """One capability that declares a scope, exposed over HTTP."""
    app = Agnara("audit")
    calls: list[str] = []

    @app.capability(scopes={"records:read"})
    def restricted() -> str:
        calls.append("restricted")
        return "private"

    http = Http("public")
    http.get("/restricted", restricted)
    asgi = http.compile(app.compile(), hooks=hooks)
    return asgi, calls


def principal_reporting_surface() -> Any:
    """A capability that reports the principal the transport built for it."""
    app = Agnara("audit")

    @app.capability
    def whoami(ctx: ExecutionContext) -> dict[str, Any]:
        return {
            "identity": ctx.principal.identity,
            "scopes": sorted(ctx.principal.scopes),
        }

    http = Http("public")
    http.get("/whoami", whoami)
    return http.compile(app.compile()), []


def test_declared_scopes_are_enforced_over_http() -> None:
    """A declared scope fails closed before an HTTP capability can run.

    The common execution plan owns this policy, so HTTP and MCP cannot assign
    different authorization meaning to the same capability declaration.
    HTTP has no principal mapper in a4 and therefore invokes anonymously.
    """
    asgi, calls = scoped_surface()

    status, _ = call(asgi, "GET", "/restricted")

    assert status == 403
    assert calls == []


def test_http_cannot_be_told_which_principal_to_use() -> None:
    """No request field is read as identity or authority.

    The HTTP surface builds an anonymous principal for every request. A
    caller naming a principal, its scopes and a bearer token changes nothing
    about the principal an explicit policy would evaluate.
    """
    asgi, _ = principal_reporting_surface()
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    run(
        asgi(
            {
                "type": "http",
                "method": "GET",
                "path": "/whoami",
                "query_string": b"scopes=records:read&principal=admin",
                "root_path": "",
                "headers": [
                    (b"authorization", b"Bearer forged"),
                    (b"x-principal", b"admin"),
                    (b"x-scopes", b"records:read"),
                    (b"cookie", b"scopes=records:read"),
                ],
            },
            receive,
            send,
        )
    )

    assert sent[0]["status"] == 200
    assert json.loads(sent[1]["body"]) == {"identity": "anonymous", "scopes": []}


class NeverConsulted:
    """A verifier that fails the test if the pipeline ever reaches it."""

    async def verify(
        self,
        evidence: Any,
        *,
        capability_id: Any,
        invocation: Any,
        principal: Any,
    ) -> Any:
        raise AssertionError("verification must not run without evidence")


def confirmation_surface() -> tuple[Http, Agnara]:
    """A confirmation-requiring capability, declared but not yet compiled."""
    app = Agnara("audit")
    calls: list[str] = []

    @app.capability(confirmation=Confirmation.REQUIRED)
    def wire_money(amount: int) -> str:
        calls.append("wire_money")
        return "sent"

    http = Http("public")
    http.post("/wire", wire_money, Binding("amount", BindingSource.BODY))
    return http, app


def test_a_confirmation_requirement_stops_the_invocation_over_http() -> None:
    """HTTP carries no evidence channel, so confirmation cannot be skipped.

    A capability declaring confirmation reports the interaction and never
    reaches its handler, rather than executing because the transport had no
    way to ask. The verifier is never consulted, because there is nothing to
    verify.
    """
    app = Agnara("audit")
    calls: list[str] = []

    @app.capability(confirmation=Confirmation.REQUIRED)
    def wire_money(amount: int) -> str:
        calls.append("wire_money")
        return "sent"

    http = Http("public")
    http.post("/wire", wire_money, Binding("amount", BindingSource.BODY))
    asgi = http.compile(app.compile(), confirmation_verifier=NeverConsulted())

    status, document = call(asgi, "POST", "/wire", b"1000")

    assert status == 428
    assert document["code"] == "interaction_required"
    assert document["details"]["kind"] == "confirmation"
    assert calls == []


def test_a_confirmation_requirement_without_a_verifier_fails_at_startup() -> None:
    """A surface cannot be compiled with an unenforceable confirmation.

    Misconfiguration is refused before the application can serve anything,
    rather than degrading into a capability that runs unconfirmed.
    """
    http, app = confirmation_surface()

    with pytest.raises(DefinitionError, match="confirmation verifier"):
        http.compile(app.compile())


def test_a_handler_exception_never_reaches_the_client() -> None:
    """An unexpected failure is redacted to one fixed sentence.

    Whatever the handler raised -- here a value that looks like a credential
    -- the response says only that the server could not complete the call.
    """
    app = Agnara("audit")

    @app.capability
    def broken() -> str:
        raise RuntimeError(f"connecting with {SECRET}")

    http = Http("public")
    http.get("/broken", broken)
    asgi = http.compile(app.compile())

    status, document = call(asgi, "GET", "/broken")

    assert status == 500
    assert document["detail"] == "The server could not complete the capability invocation."
    assert SECRET not in json.dumps(document)


def test_telemetry_events_carry_no_payload_principal_or_value() -> None:
    """Observability sees identities and outcomes, never request content."""
    app = Agnara("audit")

    @app.capability
    def transfer(account: str) -> str:
        return f"moved {account}"

    recorder = Recorder()
    http = Http("public")
    http.post("/transfer", transfer, Binding("account", BindingSource.BODY))
    asgi = http.compile(app.compile(), hooks=(recorder,))

    status, _ = call(asgi, "POST", "/transfer", json.dumps(SECRET).encode())

    assert status == 200
    assert len(recorder.events) == 2
    for event in recorder.events:
        rendered = repr(event)
        assert SECRET not in rendered
        assert "principal" not in rendered
        assert event.tracking_id is None


@pytest.mark.parametrize(
    "granted",
    [
        frozenset({"records"}),
        frozenset({"records:read:extra"}),
        frozenset({"Records:Read"}),
        frozenset({"records:read "}),
        frozenset({"records:*"}),
        frozenset({"admin"}),
    ],
)
def test_a_scope_is_matched_exactly_and_never_normalized(granted: frozenset[str]) -> None:
    """No prefix, wildcard, case fold or trim widens a granted scope.

    Every value here is a near miss for ``records:read``. If any of them
    passed, one authorization decision would depend on how a string was
    written rather than on what was granted.
    """
    policy = ScopePolicy({"records:read"})
    context = _context_for(Principal("agent", scopes=granted))

    result = run(policy.evaluate(context))

    assert type(result).__name__ == "PolicyFailure"


def test_an_exactly_granted_scope_passes() -> None:
    """The same comparison admits the scope that was actually granted."""
    policy = ScopePolicy({"records:read"})
    context = _context_for(Principal("agent", scopes=frozenset({"records:read"})))

    result = run(policy.evaluate(context))

    assert type(result).__name__ == "PolicySuccess"


def _context_for(principal: Principal) -> Any:
    from agnara.capability import CapabilityId
    from agnara.execution import Invocation

    return ExecutionContext(
        Invocation(CapabilityId("tests", "target"), {}, {}),
        DIContainer(DIRegistry()),
        principal=principal,
    )


def mcp_surface() -> tuple[McpToolInvoker, list[str]]:
    """One scope-free and one scoped capability, exposed as MCP tools."""
    app = Agnara("audit")
    calls: list[str] = []

    @app.capability
    def public_note() -> str:
        calls.append("public_note")
        return "note"

    @app.capability(scopes={"records:read"})
    def restricted() -> str:
        calls.append("restricted")
        return "private"

    mcp = Mcp(app)
    mcp.tool(public_note)
    mcp.tool(restricted)
    exposures = mcp.compile()
    registry = DIRegistry()
    plans = [ExecutionPlan.compile(app.capabilities[key], registry) for key in app.capabilities]
    invoker = McpToolInvoker(exposures, plans, DIContainer(registry))
    return invoker, calls


def context(request_id: object = 1) -> ServerRequestContext[Any]:
    class FakeContext:
        def __init__(self) -> None:
            self.request_id = request_id

    return cast("ServerRequestContext[Any]", FakeContext())


def text(result: CallToolResult) -> str:
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


def test_an_undiscoverable_mcp_tool_is_still_refused_when_called_by_name() -> None:
    """Hiding a tool is visibility; the denial is the authorization.

    An anonymous caller cannot see the scoped tool, and naming it anyway
    reaches the same refusal without running it.
    """
    invoker, calls = mcp_surface()

    hidden = next(name for name in invoker.tool_names if "restricted" in name)

    result = run(invoker(context(), CallToolRequestParams(name=hidden, arguments={})))

    assert isinstance(result, CallToolResult)
    assert result.is_error is True
    assert json.loads(text(result))["code"] == "forbidden"
    assert calls == []


def test_an_mcp_caller_cannot_supply_its_own_authority() -> None:
    """Arguments named like runtime state grant nothing.

    ``scopes`` and ``principal`` are arguments the capability never declared,
    so they are refused as unknown input rather than read as authority.
    """
    invoker, calls = mcp_surface()

    result = run(
        invoker(
            context(),
            CallToolRequestParams(
                name=next(name for name in invoker.tool_names if "restricted" in name),
                arguments={"scopes": ["records:read"], "principal": "admin"},
            ),
        )
    )

    assert isinstance(result, CallToolResult)
    assert result.is_error is True
    assert json.loads(text(result))["code"] == "forbidden"
    assert calls == []


def test_authority_shaped_arguments_are_unknown_input_even_without_a_scope() -> None:
    """The refusal is not an artefact of the scope guard running first.

    On a capability that requires no scope at all, arguments named after
    runtime state are still refused as input the capability never declared.
    """
    invoker, calls = mcp_surface()
    public = next(name for name in invoker.tool_names if "public_note" in name)

    result = run(
        invoker(
            context(),
            CallToolRequestParams(
                name=public,
                arguments={"scopes": ["records:read"], "principal": "admin"},
            ),
        )
    )

    assert isinstance(result, CallToolResult)
    assert result.is_error is True
    assert json.loads(text(result))["code"] == "invalid_input"
    assert calls == []
