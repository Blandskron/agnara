"""A4-09: one semantic contract across direct, HTTP and MCP surfaces."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, cast

import pytest
from mcp.server import ServerRequestContext
from mcp_types import (
    CallToolRequestParams,
    CallToolResult,
    ElicitRequestFormParams,
    InputRequiredResult,
    TextContent,
)

from agnara import Agnara, CapabilityDefinition, CapabilityId, Confirmation, Risk
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    Success,
    invoke_result,
)
from agnara.policy import PolicyFailure, Principal
from agnara.schema import materialize_json
from agnara_http import Binding, BindingSource, Http, OpenApiInfo, OpenApiOperation
from agnara_http._problem import _serialize_failure
from agnara_mcp import Mcp, McpToolInvoker, project_mcp_result, project_mcp_tools


class Tier(Enum):
    FREE = "free"
    PRO = "pro"


@dataclass(frozen=True)
class Profile:
    tier: Tier
    labels: list[str]
    scores: dict[str, int]
    coordinates: tuple[int, int]
    nickname: str | None = None
    mode: Literal["safe", "fast"] = "safe"


def _context(
    plan: ExecutionPlan,
    payload: dict[str, Any],
    *,
    principal: Principal | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        Invocation(plan.definition.id, payload, {}),
        DIContainer(DIRegistry()),
        principal=principal,
    )


def _request(asgi: Any, body: object, *, path: str = "/profiles") -> tuple[int, dict[str, Any]]:
    events: list[dict[str, Any]] = []
    incoming = [{"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}]

    async def receive() -> dict[str, Any]:
        return incoming.pop(0)

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    asyncio.run(
        asgi(
            {
                "type": "http",
                "method": "POST",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [(b"content-type", b"application/json")],
                "root_path": "",
            },
            receive,
            send,
        )
    )
    payload = b"".join(event.get("body", b"") for event in events[1:])
    return events[0]["status"], json.loads(payload)


@dataclass
class _McpContext:
    request_id: object = 1


def _mcp_call(invoker: McpToolInvoker, name: str, arguments: dict[str, Any]) -> CallToolResult:
    context = cast("ServerRequestContext[Any]", _McpContext())
    result = asyncio.run(invoker(context, CallToolRequestParams(name=name, arguments=arguments)))
    assert isinstance(result, CallToolResult)
    return result


def _mcp_payload(result: CallToolResult) -> dict[str, Any]:
    block = result.content[0]
    assert isinstance(block, TextContent)
    return cast(dict[str, Any], json.loads(block.text))


def test_supported_schema_graph_is_one_semantic_contract_on_all_surfaces() -> None:
    app = Agnara("contracts")

    @app.capability
    def accept(profile: Profile) -> dict[str, Any]:
        return {
            "tier": profile.tier.value,
            "labels": profile.labels,
            "scores": profile.scores,
            "coordinates": list(profile.coordinates),
            "nickname": profile.nickname,
            "mode": profile.mode,
        }

    definition = app.capabilities["contracts.accept"]
    plan = ExecutionPlan.compile(definition, DIRegistry())
    mcp = Mcp(app)
    mcp.tool(accept)
    mcp_tools = mcp.compile()
    tool = project_mcp_tools(mcp_tools, [plan])[0]
    http = Http()
    http.post(
        "/profiles",
        accept,
        Binding("profile", BindingSource.BODY),
        openapi=OpenApiOperation(),
    )
    asgi = http.compile(app.compile(), openapi=OpenApiInfo("Contracts", "1"))

    core_schema = dict(plan.input_schemas["profile"].json_schema())
    http_schema = asgi.openapi()["paths"]["/profiles"]["post"]["requestBody"]["content"]
    http_schema = http_schema["application/json"]["schema"]
    mcp_schema = tool.input_schema["properties"]["profile"]
    assert core_schema == http_schema == mcp_schema
    assert tool.input_schema["required"] == ["profile"]
    assert core_schema["required"] == ["tier", "labels", "scores", "coordinates"]

    python_value = Profile(Tier.PRO, ["a"], {"quality": 5}, (3, 4))
    direct = asyncio.run(invoke_result(plan, _context(plan, {"profile": python_value})))
    strict_rejection = asyncio.run(
        invoke_result(plan, _context(plan, {"profile": {"tier": "pro"}}))
    )
    wire_value = {
        "tier": "pro",
        "labels": ["a"],
        "scores": {"quality": 5},
        "coordinates": [3, 4],
    }
    http_status, http_value = _request(asgi, wire_value)
    invoker = McpToolInvoker(mcp_tools, [plan], DIContainer(DIRegistry()))
    mcp_value = _mcp_call(invoker, "contracts.accept", {"profile": wire_value})

    assert isinstance(direct, Success)
    assert isinstance(strict_rejection, Failure)
    assert strict_rejection.code is FailureCode.INVALID_INPUT
    assert http_status == 200
    assert http_value == direct.value
    assert mcp_value.structured_content == {"result": direct.value}


_MATERIALIZATION_EFFECTS: list[str] = []


@dataclass
class GuardedInput:
    value: int

    def __post_init__(self) -> None:
        _MATERIALIZATION_EFFECTS.append("constructed")


class BusinessRule:
    async def evaluate(self, context: ExecutionContext) -> PolicyFailure:
        del context
        _MATERIALIZATION_EFFECTS.append("business-policy")
        return PolicyFailure("business rule denied")


def test_scope_policy_precedes_business_policy_materialization_and_handler() -> None:
    _MATERIALIZATION_EFFECTS.clear()

    def guarded(value: GuardedInput) -> str:
        _MATERIALIZATION_EFFECTS.append("handler")
        return str(value.value)

    definition = CapabilityDefinition(
        id=CapabilityId("policy", "guarded"),
        handler=guarded,
        scopes=frozenset({"records:write"}),
        policies=(BusinessRule(),),
    )
    plan = ExecutionPlan.compile(definition, DIRegistry())
    app = Agnara("policy")
    app.capabilities.register(definition)
    mcp = Mcp(app)
    mcp.tool(definition)
    mcp_tools = mcp.compile()
    http = Http()
    http.post("/guarded", definition, Binding("value", BindingSource.BODY))
    asgi = http.compile(app.compile())

    http_status, http_failure = _request(asgi, {"value": 1}, path="/guarded")
    mcp_failure = _mcp_call(
        McpToolInvoker(mcp_tools, [plan], DIContainer(DIRegistry())),
        "policy.guarded",
        {"value": {"value": 1}},
    )
    assert http_status == 403
    assert http_failure["code"] == "forbidden"
    assert _mcp_payload(mcp_failure)["code"] == "forbidden"
    assert _MATERIALIZATION_EFFECTS == []

    denied = asyncio.run(
        invoke_result(
            plan,
            _context(plan, {"value": {"value": 1}}),
            input_materializer=materialize_json,
        )
    )
    assert isinstance(denied, Failure)
    assert denied.code is FailureCode.FORBIDDEN
    assert _MATERIALIZATION_EFFECTS == []

    allowed_scope = asyncio.run(
        invoke_result(
            plan,
            _context(
                plan,
                {"value": {"value": 1}},
                principal=Principal("writer", scopes={"records:write"}),
            ),
            input_materializer=materialize_json,
        )
    )
    assert isinstance(allowed_scope, Failure)
    assert allowed_scope.message == "business rule denied"
    assert _MATERIALIZATION_EFFECTS == ["business-policy"]


def test_risk_and_effects_stay_metadata_and_never_grant_or_deny_authority() -> None:
    def destructive() -> str:
        return "done"

    definition = CapabilityDefinition(
        id=CapabilityId("metadata", "destructive"),
        handler=destructive,
        effects=frozenset({"delete"}),
        risk=Risk.HIGH,
        confirmation=Confirmation.NEVER,
    )
    plan = ExecutionPlan.compile(definition, DIRegistry())
    assert plan.policies == ()
    assert asyncio.run(invoke_result(plan, _context(plan, {}))) == Success("done")


@dataclass
class ExplodingInput:
    value: int

    def __post_init__(self) -> None:
        raise RuntimeError("credential=C:/private/secret.txt")


def test_unexpected_wire_constructor_failure_is_redacted_on_both_transports() -> None:
    app = Agnara("redaction")

    @app.capability
    def accept(value: ExplodingInput) -> str:  # pragma: no cover - construction fails first
        return str(value.value)

    definition = app.capabilities["redaction.accept"]
    plan = ExecutionPlan.compile(definition, DIRegistry())
    mcp = Mcp(app)
    mcp.tool(accept)
    mcp_tools = mcp.compile()
    http = Http()
    http.post("/guarded", accept, Binding("value", BindingSource.BODY))
    asgi = http.compile(app.compile())

    http_status, http_failure = _request(asgi, {"value": 1}, path="/guarded")
    mcp_failure = _mcp_call(
        McpToolInvoker(mcp_tools, [plan], DIContainer(DIRegistry())),
        "redaction.accept",
        {"value": {"value": 1}},
    )

    assert http_status == 500
    assert http_failure["detail"] == "The server could not complete the capability invocation."
    assert _mcp_payload(mcp_failure) == {
        "code": "internal_failure",
        "message": "capability invocation failed",
    }
    assert "private" not in json.dumps(http_failure)
    assert "private" not in json.dumps(mcp_failure.model_dump(mode="json"))


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (FailureCode.INVALID_INPUT, 400),
        (FailureCode.UNAUTHENTICATED, 401),
        (FailureCode.FORBIDDEN, 403),
        (FailureCode.NOT_FOUND, 404),
        (FailureCode.CONFLICT, 409),
        (FailureCode.RATE_LIMITED, 429),
        (FailureCode.UNAVAILABLE, 503),
        (FailureCode.TIMEOUT, 504),
        (FailureCode.INTERNAL_FAILURE, 500),
    ],
)
def test_failure_mapping_and_redaction_matrix(code: FailureCode, status: int) -> None:
    failure = (
        Failure(code, "secret=C:/private/token.txt", {"credential": "raw-secret"})
        if code is FailureCode.INTERNAL_FAILURE
        else Failure(code, "caller-safe message", {"field": "caller-safe"})
    )
    http = _serialize_failure(failure)
    http_payload = json.loads(http.body)
    mcp_payload = _mcp_payload(cast(CallToolResult, project_mcp_result(failure)))

    assert http.status == status
    assert http_payload["code"] == mcp_payload["code"] == code.value
    assert "credential" not in mcp_payload
    if code is FailureCode.INTERNAL_FAILURE:
        assert http_payload["detail"] == "The server could not complete the capability invocation."
        assert mcp_payload["message"] == "capability invocation failed"
        assert "private" not in json.dumps(http_payload)
        assert "raw-secret" not in json.dumps(http_payload)
        assert "private" not in json.dumps(mcp_payload)
    else:
        assert http_payload["detail"] == mcp_payload["message"] == failure.message
        assert http_payload["details"] == {"field": "caller-safe"}


def test_confirmation_failure_has_protocol_specific_safe_interaction_shapes() -> None:
    failure = Failure(
        FailureCode.INTERACTION_REQUIRED,
        "A verified approval is required.",
        {
            "kind": "confirmation",
            "title": "Approve transfer",
            "capability_id": "payments.transfer",
            "hints": (),
        },
    )
    http = _serialize_failure(failure)
    mcp = project_mcp_result(failure)

    assert http.status == 428
    assert json.loads(http.body)["code"] == "interaction_required"
    assert isinstance(mcp, InputRequiredResult)
    assert mcp.input_requests is not None
    request = mcp.input_requests["confirmation"]
    assert isinstance(request.params, ElicitRequestFormParams)
    assert request.params.requested_schema["required"] == ["confirmed"]
    assert "evidence" not in json.dumps(mcp.model_dump(mode="json"))
