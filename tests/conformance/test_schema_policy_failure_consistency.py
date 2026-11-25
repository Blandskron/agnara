"""A4-09: one semantic contract across direct, HTTP, MCP and inbound event surfaces."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
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
from agnara_events import (
    CLOUDEVENTS_JSON_CONTENT_TYPE,
    AsyncAPIExportError,
    AsyncAPIInfo,
    ConsumerBudgets,
    ConsumerDiagnostic,
    SettlementAction,
    compile_inbound_event,
    consume_inbound_events,
    declare_inbound_event,
    project_asyncapi,
)
from agnara_http import Binding, BindingSource, Http, OpenApiInfo, OpenApiOperation
from agnara_http._problem import _serialize_failure
from agnara_mcp import Mcp, McpToolInvoker, project_mcp_result, project_mcp_tools


class Tier(Enum):
    FREE = "free"
    PRO = "pro"


class _NumberChoice(Enum):
    ZERO = 0
    ONE = 1


@pytest.mark.parametrize("value", [True, False])
def test_boolean_json_cannot_select_a_numeric_enum_on_http_or_mcp(value: bool) -> None:
    app = Agnara("enum_contract")
    calls: list[_NumberChoice] = []

    @app.capability
    def accept(choice: _NumberChoice) -> str:
        calls.append(choice)
        return choice.name

    definition = app.capabilities["enum_contract.accept"]
    plan = ExecutionPlan.compile(definition, DIRegistry())
    http = Http()
    http.post("/choice", accept, Binding("choice", BindingSource.BODY))
    status, failure = _request(http.compile(app.compile()), value, path="/choice")
    assert status == 400
    assert failure["code"] == "invalid_input"
    assert failure["details"]["path"] == ["choice"]

    mcp = Mcp(app)
    mcp.tool(accept)
    result = _mcp_call(
        McpToolInvoker(mcp.compile(), [plan], DIContainer(DIRegistry())),
        "enum_contract.accept",
        {"choice": value},
    )
    assert result.is_error is True
    assert _mcp_payload(result)["code"] == "invalid_input"

    event_diagnostic, event_settlement = _events_call(definition, plan, {"choice": value})
    assert event_diagnostic.outcome == "invalid_input"
    assert event_settlement == SettlementAction.REJECT.value
    assert calls == []


@pytest.mark.parametrize(
    ("value", "expected"), [(1.0, 1), (2.0, 2), (True, None), (3.0, None), ("1", None)]
)
def test_numeric_literal_inputs_agree_on_http_and_mcp(value: object, expected: int | None) -> None:
    app = Agnara("literal_contract")
    calls: list[int] = []

    @app.capability
    def accept(choice: Literal[1, 2]) -> dict[str, int]:
        assert type(choice) is int
        calls.append(choice)
        return {"choice": choice}

    definition = app.capabilities["literal_contract.accept"]
    plan = ExecutionPlan.compile(definition, DIRegistry())
    direct = asyncio.run(invoke_result(plan, _context(plan, {"choice": value})))
    assert isinstance(direct, Failure)
    assert direct.code is FailureCode.INVALID_INPUT
    assert calls == []

    http = Http()
    http.post("/choice", accept, Binding("choice", BindingSource.BODY))
    status, payload = _request(http.compile(app.compile()), value, path="/choice")
    mcp = Mcp(app)
    mcp.tool(accept)
    result = _mcp_call(
        McpToolInvoker(mcp.compile(), [plan], DIContainer(DIRegistry())),
        "literal_contract.accept",
        {"choice": value},
    )
    event_diagnostic, event_settlement = _events_call(definition, plan, {"choice": value})
    if expected is None:
        assert status == 400
        assert payload["code"] == "invalid_input"
        assert payload["details"]["path"] == ["choice"]
        assert result.is_error is True
        assert _mcp_payload(result)["code"] == "invalid_input"
        assert event_diagnostic.outcome == "invalid_input"
        assert event_settlement == SettlementAction.REJECT.value
        assert calls == []
    else:
        assert status == 200
        assert payload == {"choice": expected}
        assert result.is_error is False
        assert result.structured_content == {"result": {"choice": expected}}
        assert event_diagnostic.outcome == "success"
        assert event_settlement == SettlementAction.ACKNOWLEDGE.value
        assert calls == [expected, expected, expected]


@dataclass(frozen=True)
class Draft07Profile:
    tier: Tier
    labels: list[str]
    scores: dict[str, int]
    coordinates: tuple[int, int]
    mode: Literal["safe", "fast"] = "safe"


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


@dataclass
class _EventDelivery:
    body: bytes
    content_type: str | None = CLOUDEVENTS_JSON_CONTENT_TYPE
    actions: list[str] = field(default_factory=list)

    async def acknowledge(self) -> None:
        self.actions.append(SettlementAction.ACKNOWLEDGE.value)

    async def reject(self) -> None:
        self.actions.append(SettlementAction.REJECT.value)

    async def release(self) -> None:
        self.actions.append(SettlementAction.RELEASE.value)


class _SingleEventSource:
    def __init__(self, delivery: _EventDelivery) -> None:
        self._delivery: _EventDelivery | None = delivery

    async def receive(self) -> _EventDelivery | None:
        delivery, self._delivery = self._delivery, None
        return delivery

    async def stop_receiving(self) -> None:
        return None


def _events_call(
    definition: CapabilityDefinition,
    plan: ExecutionPlan,
    data: object,
    *,
    principal: Principal | None = None,
) -> tuple[ConsumerDiagnostic, str]:
    exposure = declare_inbound_event(
        definition,
        subscription_id="conformance-sub",
        event_type="example.conformance.v1",
        principal=principal if principal is not None else Principal("events-worker"),
    )
    binding = compile_inbound_event(exposure, {definition.id: plan})
    envelope = json.dumps(
        {
            "specversion": "1.0",
            "id": "evt-conformance-1",
            "source": "urn:agnara:conformance",
            "type": "example.conformance.v1",
            "datacontenttype": "application/json",
            "data": data,
        }
    ).encode("utf-8")
    delivery = _EventDelivery(envelope)

    async def run() -> tuple[ConsumerDiagnostic, str]:
        container = DIContainer(DIRegistry())
        try:
            diagnostics = await consume_inbound_events(
                binding,
                container,
                _SingleEventSource(delivery),
                budgets=ConsumerBudgets(attempt_seconds=5.0, shutdown_seconds=1.0),
                stop_event=asyncio.Event(),
            )
            assert len(diagnostics) == 1
            assert len(delivery.actions) == 1
            return diagnostics[0], delivery.actions[0]
        finally:
            await container.aclose()

    return asyncio.run(run())


@pytest.mark.parametrize("value", [10**400, -(10**400)], ids=["positive", "negative"])
def test_out_of_range_json_float_is_invalid_input_on_every_json_surface(value: int) -> None:
    app = Agnara("numbers")
    calls: list[float] = []

    @app.capability
    def accept(factor: float) -> float:
        calls.append(factor)
        return factor

    definition = app.capabilities["numbers.accept"]
    plan = ExecutionPlan.compile(definition, DIRegistry())
    direct = asyncio.run(
        invoke_result(plan, _context(plan, {"factor": value}), input_materializer=materialize_json)
    )
    assert isinstance(direct, Failure)
    assert direct.code is FailureCode.INVALID_INPUT
    assert direct.details["path"] == ("factor",)

    http = Http()
    http.post("/numbers", accept, Binding("factor", BindingSource.BODY))
    status, http_failure = _request(http.compile(app.compile()), value, path="/numbers")
    assert status == 400
    assert http_failure["code"] == "invalid_input"
    assert http_failure["details"]["path"] == ["factor"]

    mcp = Mcp(app)
    mcp.tool(accept)
    result = _mcp_call(
        McpToolInvoker(mcp.compile(), [plan], DIContainer(DIRegistry())),
        "numbers.accept",
        {"factor": value},
    )
    assert result.is_error is True
    assert _mcp_payload(result)["code"] == "invalid_input"
    assert _mcp_payload(result)["message"] == "integer is outside the float range"

    event_diagnostic, event_settlement = _events_call(definition, plan, {"factor": value})
    assert event_diagnostic.outcome == "invalid_input"
    assert event_settlement == SettlementAction.REJECT.value
    assert calls == []


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
    event_binding = compile_inbound_event(
        declare_inbound_event(
            definition,
            subscription_id="contracts-accept",
            event_type="example.contracts.accept.v1",
            principal=Principal("events-worker"),
            public_address="contracts.accept.v1",
        ),
        {definition.id: plan},
    )
    # ADR 0101 Draft-07 export intentionally rejects `anyOf` unions such as `str | None`,
    # while a union-free graph projects directly into AsyncAPI 3.1.0.
    with pytest.raises(AsyncAPIExportError, match="anyOf"):
        project_asyncapi([event_binding], AsyncAPIInfo("Contracts", "1"))

    draft07_app = Agnara("draft07_contracts")

    @draft07_app.capability
    def accept_strict(profile: Draft07Profile) -> str:
        return profile.tier.value

    strict_definition = draft07_app.capabilities["draft07_contracts.accept_strict"]
    strict_plan = ExecutionPlan.compile(strict_definition, DIRegistry())
    strict_event_binding = compile_inbound_event(
        declare_inbound_event(
            strict_definition,
            subscription_id="contracts-accept",
            event_type="example.contracts.accept.v1",
            principal=Principal("events-worker"),
            public_address="contracts.accept.v1",
        ),
        {strict_definition.id: strict_plan},
    )
    asyncapi = project_asyncapi([strict_event_binding], AsyncAPIInfo("Contracts", "1"))
    event_data_schema = asyncapi["components"]["messages"]["contracts-acceptMessage"]["payload"][
        "schema"
    ]["properties"]["data"]
    event_profile_schema = event_data_schema["properties"]["profile"]

    core_schema = dict(plan.input_schemas["profile"].json_schema())
    http_schema = asgi.openapi()["paths"]["/profiles"]["post"]["requestBody"]["content"]
    http_schema = http_schema["application/json"]["schema"]
    mcp_schema = tool.input_schema["properties"]["profile"]
    assert core_schema == http_schema == mcp_schema
    assert tool.input_schema["required"] == event_data_schema["required"] == ["profile"]
    assert (
        core_schema["required"]
        == event_profile_schema["required"]
        == ["tier", "labels", "scores", "coordinates"]
    )
    assert event_profile_schema["properties"]["coordinates"] == {
        "type": "array",
        "items": [{"type": "integer"}, {"type": "integer"}],
        "additionalItems": False,
        "minItems": 2,
        "maxItems": 2,
    }

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
    event_ok, event_ok_settlement = _events_call(definition, plan, {"profile": wire_value})
    event_bad, event_bad_settlement = _events_call(definition, plan, {"profile": {"tier": "pro"}})

    assert isinstance(direct, Success)
    assert isinstance(strict_rejection, Failure)
    assert strict_rejection.code is FailureCode.INVALID_INPUT
    assert http_status == 200
    assert http_value == direct.value
    assert mcp_value.structured_content == {"result": direct.value}
    assert event_ok.outcome == "success"
    assert event_ok_settlement == SettlementAction.ACKNOWLEDGE.value
    assert event_bad.outcome == "invalid_input"
    assert event_bad_settlement == SettlementAction.REJECT.value


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
    event_failure, event_settlement = _events_call(definition, plan, {"value": {"value": 1}})
    assert http_status == 403
    assert http_failure["code"] == "forbidden"
    assert http_failure["detail"] == "required scopes not granted"
    assert _mcp_payload(mcp_failure)["code"] == "forbidden"
    assert _mcp_payload(mcp_failure)["message"] == "required scopes not granted"
    assert event_failure.outcome == "forbidden"
    assert event_settlement == SettlementAction.REJECT.value
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
    assert denied.message == "required scopes not granted"
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
    event_failure, event_settlement = _events_call(definition, plan, {"value": {"value": 1}})

    assert http_status == 500
    assert http_failure["detail"] == "The server could not complete the capability invocation."
    assert _mcp_payload(mcp_failure) == {
        "code": "internal_failure",
        "message": "capability invocation failed",
    }
    assert event_failure.outcome == "internal_failure"
    assert event_settlement == SettlementAction.RELEASE.value
    assert "private" not in json.dumps(http_failure)
    assert "private" not in json.dumps(mcp_failure.model_dump(mode="json"))
    assert "private" not in repr(event_failure)


@pytest.mark.parametrize(
    ("code", "expected_settlement"),
    [
        (FailureCode.INVALID_INPUT, SettlementAction.REJECT.value),
        (FailureCode.UNAUTHENTICATED, SettlementAction.REJECT.value),
        (FailureCode.FORBIDDEN, SettlementAction.REJECT.value),
        (FailureCode.NOT_FOUND, SettlementAction.REJECT.value),
        (FailureCode.CONFLICT, SettlementAction.REJECT.value),
        (FailureCode.RATE_LIMITED, SettlementAction.RELEASE.value),
        (FailureCode.UNAVAILABLE, SettlementAction.RELEASE.value),
        (FailureCode.TIMEOUT, SettlementAction.RELEASE.value),
        (FailureCode.INTERNAL_FAILURE, SettlementAction.RELEASE.value),
    ],
)
def test_events_failure_settlement_matrix_matches_canonical_codes(
    code: FailureCode,
    expected_settlement: str,
) -> None:
    app = Agnara("event_matrix")

    @app.capability
    def fail_with() -> Failure:
        return Failure(
            code,
            "secret=C:/private/token.txt",
            {"credential": "raw-secret"},
        )

    definition = app.capabilities["event_matrix.fail_with"]
    plan = ExecutionPlan.compile(definition, DIRegistry())
    diagnostic, settlement = _events_call(definition, plan, {})

    assert diagnostic.outcome == code.value
    assert settlement == diagnostic.settlement == expected_settlement
    assert "private" not in repr(diagnostic)
    assert "raw-secret" not in repr(diagnostic)


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
