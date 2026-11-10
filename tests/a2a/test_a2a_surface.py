"""ADR 0098 profile through the public `agnara_a2a` surface and the official SDK client.

Requests traverse HTTPX's in-process ASGI transport, the admission gate and
the SDK's JSON-RPC dispatcher. No adapter handler is called directly. The
principal resolver stands in for the host's authentication boundary.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any, cast

import httpx
import pytest
from a2a.client.transports.jsonrpc import JsonRpcTransport
from a2a.types import a2a_pb2
from google.protobuf import json_format

from agnara import Agnara, CapabilityDefinition, Confirmation, Principal
from agnara.di import DIContainer, DIRegistry
from agnara.execution import ExecutionContext, ExecutionPlan, Failure, FailureCode
from agnara_a2a import (
    A2A_PROTOCOL_VERSION,
    A2A_PYTHON_SDK_VERSION,
    SUPPORTED_A2A_PROTOCOL_VERSIONS,
    A2a,
    A2aAgentCard,
    A2aDefinitionError,
    A2aSkillExposure,
    build_a2a_app,
)

URL = "http://agent.test/"
CARD = A2aAgentCard(name="Calculator", description="Adds numbers", version="2026.10")
TOKENS = {b"Bearer alice": "alice", b"Bearer admin": "admin"}
ALICE = {"Authorization": "Bearer alice", "A2A-Version": "1.0"}
ADMIN = {"Authorization": "Bearer admin", "A2A-Version": "1.0"}
CHALLENGE = 'Bearer realm="agent.test"'


def principals(scope: Mapping[str, Any]) -> Principal | None:
    """Host authentication stand-in: a fixed token table, never a claim."""
    header = dict(scope["headers"]).get(b"authorization", b"")
    identity = TOKENS.get(header)
    if identity is None:
        return None
    return Principal(identity, scopes={"calc:admin"} if identity == "admin" else set())


def build_app() -> tuple[Agnara, dict[str, Any]]:
    app = Agnara("calc")
    state: dict[str, Any] = {"effects": 0}

    @app.capability(output=int)
    def add(a: int, b: int) -> int:
        return a + b

    @app.capability(output=tuple[int, int])
    def pair() -> tuple[int, int]:
        return (1, 2)

    @app.capability(output=str)
    def outcome(code: str) -> str | Failure:
        return Failure(FailureCode(code), f"canonical {code} message")

    @app.capability(scopes=("calc:admin",), output=str)
    def admin_only() -> str:
        state["effects"] += 1
        return "done"

    @app.capability(output=str)
    def explode() -> str:
        raise RuntimeError("secret-token-xyz in /srv/private/path")

    @app.capability(output=int)
    def huge() -> int:
        return 2**60

    @app.capability
    def nest(levels: int) -> Any:
        value: Any = 0
        for _ in range(levels):
            value = {"n": value}
        return value

    @app.capability(output=str)
    async def slow() -> str:
        await asyncio.sleep(10)
        return "late"

    @app.capability(output=dict[str, Any])
    async def whoami(context: ExecutionContext) -> dict[str, Any]:
        return {
            "identity": context.principal.identity,
            "metadata": dict(context.invocation.metadata),
        }

    @app.capability(confirmation="required", output=str)
    def guarded() -> str:
        return "approved"

    return app, state


def definition(app: Agnara, name: str) -> CapabilityDefinition:
    return next(app.capabilities[cid] for cid in app.capabilities if cid.name == name)


def expose(app: Agnara, name: str) -> A2aSkillExposure:
    a2a = A2a(app)
    a2a.skill(
        definition(app, name),
        id=name,
        name=name.title(),
        description=f"Runs {name}",
        tags=("calc",),
    )
    return a2a.compile()


def plans_of(app: Agnara) -> list[ExecutionPlan]:
    registry = DIRegistry()
    return [
        ExecutionPlan.compile(d, registry)
        for d in app.compile().values()
        if d.confirmation is not Confirmation.REQUIRED
    ]


def run[T](coroutine: Any) -> T:
    async def bounded() -> T:
        async with asyncio.timeout(30):
            return await coroutine

    return asyncio.run(bounded())


@asynccontextmanager
async def serve(
    name: str, *, app: Agnara | None = None, **options: Any
) -> AsyncIterator[tuple[httpx.AsyncClient, JsonRpcTransport, dict[str, Any]]]:
    if app is None:
        app, state = build_app()
    else:
        state = {}
    container = DIContainer(DIRegistry())
    asgi = build_a2a_app(
        expose(app, name),
        plans_of(app),
        container,
        card=CARD,
        url=URL,
        principals=principals,
        challenge=CHALLENGE,
        **options,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=asgi), base_url="http://agent.test", headers=ALICE
    ) as http:
        card = json_format.ParseDict(
            (await http.get("/.well-known/agent-card.json")).json(), a2a_pb2.AgentCard()
        )
        async with JsonRpcTransport(http, card, URL, is_shared_httpx=True) as client:
            yield http, client, state
    await container.aclose()


def message(data: Any, **extra: Any) -> dict[str, Any]:
    return {"messageId": "client-message", "role": "ROLE_USER", "parts": [{"data": data}], **extra}


async def rpc(
    http: httpx.AsyncClient, params: Any, method: str = "SendMessage", **kwargs: Any
) -> dict[str, Any]:
    reply = await http.post(
        "/", json={"jsonrpc": "2.0", "id": "t", "method": method, "params": params}, **kwargs
    )
    assert reply.status_code == 200, reply.text
    return reply.json()


async def error_of(http: httpx.AsyncClient, params: Any, **kwargs: Any) -> dict[str, Any]:
    body = await rpc(http, params, **kwargs)
    assert "error" in body, body
    return body["error"]


def agnara_code(error: Mapping[str, Any]) -> str | None:
    for item in error.get("data", []):
        if "ErrorInfo" in item.get("@type", ""):
            return item.get("metadata", {}).get("agnaraCode")
    return None


def result_of(body: Mapping[str, Any]) -> Any:
    return body["result"]["message"]["parts"][0]["data"]["result"]


def test_identities_are_the_exact_pins() -> None:
    assert version("a2a-sdk") == A2A_PYTHON_SDK_VERSION == "1.3.0"
    assert SUPPORTED_A2A_PROTOCOL_VERSIONS == (A2A_PROTOCOL_VERSION,) == ("1.0",)


def test_a_message_round_trips_through_the_official_client() -> None:
    async def scenario() -> None:
        async with serve("add") as (_, client, _state):
            request = json_format.ParseDict(
                {"message": message({"a": 2, "b": 3})}, a2a_pb2.SendMessageRequest()
            )
            answer = await client.send_message(request)
            assert answer.WhichOneof("payload") == "message"
            parsed = json_format.MessageToDict(answer.message)
            assert parsed["role"] == "ROLE_AGENT"
            assert parsed["messageId"] != "client-message"
            assert "contextId" not in parsed and "taskId" not in parsed
            assert parsed["parts"] == [
                {"data": {"result": 5.0}, "mediaType": "application/json"}
            ] or parsed["parts"] == [{"data": {"result": 5}, "mediaType": "application/json"}]

    run(scenario())


def test_the_numeric_domain_is_normalized_and_bounded() -> None:
    async def scenario() -> None:
        async with serve("add") as (http, _, _state):
            assert result_of(await rpc(http, {"message": message({"a": 2**53 - 1, "b": 0})})) == (
                2**53 - 1
            )
            fraction = await error_of(http, {"message": message({"a": 2.5, "b": 1})})
            assert fraction["code"] == -32602 and agnara_code(fraction) == "invalid_input"
            big = await error_of(http, {"message": message({"a": 2**53, "b": 0})})
            assert big["code"] == -32602 and agnara_code(big) == "invalid_input"
            assert big["message"] == "number outside the supported domain"

    run(scenario())


PROTOCOL_ROWS = {
    "taskId": ({"message": message({"a": 1, "b": 1}, taskId="t")}, -32001),
    "contextId": ({"message": message({"a": 1, "b": 1}, contextId="c")}, -32004),
    "referenceTaskIds": ({"message": message({"a": 1, "b": 1}, referenceTaskIds=["t"])}, -32004),
    "extensions": ({"message": message({"a": 1, "b": 1}, extensions=["urn:x"])}, -32004),
    "role": ({"message": {**message({"a": 1, "b": 1}), "role": "ROLE_AGENT"}}, -32602),
    "two_parts": (
        {"message": {**message({}), "parts": [{"data": {"a": 1}}, {"data": {"b": 1}}]}},
        -32602,
    ),
    "text_part": ({"message": {**message({}), "parts": [{"text": "1 + 1"}]}}, -32005),
    "media_type": (
        {"message": {**message({}), "parts": [{"data": {"a": 1}, "mediaType": "text/csv"}]}},
        -32005,
    ),
    "list_data": ({"message": message([1, 2])}, -32602),
    "tenant": ({"tenant": "other", "message": message({"a": 1, "b": 1})}, -32602),
    "push": (
        {
            "message": message({"a": 1, "b": 1}),
            "configuration": {"taskPushNotificationConfig": {"url": "https://agent.test/p"}},
        },
        -32003,
    ),
    "output_mode": (
        {
            "message": message({"a": 1, "b": 1}),
            "configuration": {"acceptedOutputModes": ["text/plain"]},
        },
        -32005,
    ),
}


@pytest.mark.parametrize("row", sorted(PROTOCOL_ROWS))
def test_out_of_profile_requests_are_refused_before_invocation(row: str) -> None:
    params, code = PROTOCOL_ROWS[row]

    async def scenario() -> None:
        async with serve("admin_only") as (http, _, state):
            error = await error_of(http, params, headers=ADMIN)
            assert error["code"] == code, error
            assert state["effects"] == 0

    run(scenario())


def test_unrecognized_fields_select_nothing() -> None:
    async def scenario() -> None:
        async with serve("add") as (http, _, _state):
            body = await rpc(
                http,
                {
                    "message": {**message({"a": 4, "b": 4}), "capabilityId": "calc.explode"},
                    "metadata": {"capability": "calc.explode"},
                    "configuration": {"historyLength": 3, "returnImmediately": True},
                },
            )
            assert result_of(body) == 8

    run(scenario())


@pytest.mark.parametrize("revision", [None, "", "0.3", "1.99", "1.0.0", "01.0"])
def test_unreviewed_revisions_are_refused_by_the_gate(revision: str | None) -> None:
    async def scenario() -> None:
        async with serve("add") as (http, _, _state):
            headers = {"Authorization": "Bearer alice"}
            if revision is not None:
                headers["A2A-Version"] = revision
            http.headers.pop("A2A-Version")
            reply = await http.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "SendMessage",
                    "params": {"message": message({"a": 1, "b": 1})},
                },
                headers=headers,
            )
            body = reply.json()
            assert body["id"] == 7 and body["error"]["code"] == -32009

    run(scenario())


def test_authentication_is_refused_before_the_body_is_parsed() -> None:
    async def scenario() -> None:
        async with serve("add") as (http, _, _state):
            for authorization in ("", "Bearer forged"):
                reply = await http.post(
                    "/", content=b"{not json", headers={"Authorization": authorization}
                )
                assert reply.status_code == 401
                assert reply.headers["www-authenticate"] == CHALLENGE
                assert reply.content == b""

    run(scenario())


def test_policy_denies_before_effects_and_principals_stay_isolated() -> None:
    async def scenario() -> None:
        async with serve("admin_only") as (http, _, state):
            denied = await error_of(http, {"message": message({})})
            assert denied["code"] == -32603 and agnara_code(denied) == "forbidden"
            assert state["effects"] == 0
            allowed = await rpc(http, {"message": message({})}, headers=ADMIN)
            assert result_of(allowed) == "done" and state["effects"] == 1

    run(scenario())


def test_the_capability_context_receives_no_headers_or_credentials() -> None:
    async def scenario() -> None:
        async with serve("whoami") as (http, _, _state):
            replies = await asyncio.gather(
                rpc(http, {"message": message({})}),
                rpc(http, {"message": message({})}, headers=ADMIN),
            )
            assert [result_of(reply) for reply in replies] == [
                {"identity": "alice", "metadata": {"transport": "a2a"}},
                {"identity": "admin", "metadata": {"transport": "a2a"}},
            ]

    run(scenario())


@pytest.mark.parametrize(
    ("code", "rpc_code"),
    [(code, -32602 if code is FailureCode.INVALID_INPUT else -32603) for code in FailureCode],
)
def test_every_canonical_failure_carries_its_category(code: FailureCode, rpc_code: int) -> None:
    async def scenario() -> None:
        async with serve("outcome") as (http, _, _state):
            error = await error_of(http, {"message": message({"code": code.value})})
            assert error["code"] == rpc_code
            assert agnara_code(error) == code.value

    run(scenario())


@pytest.mark.parametrize(
    ("name", "payload"), [("explode", {}), ("huge", {}), ("nest", {"levels": 40})]
)
def test_unexpected_and_unrepresentable_results_are_redacted(
    name: str, payload: dict[str, Any]
) -> None:
    async def scenario() -> None:
        async with serve(name) as (http, _, _state):
            reply = await http.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "id": "t",
                    "method": "SendMessage",
                    "params": {"message": message(payload)},
                },
            )
            error = reply.json()["error"]
            assert error["code"] == -32603 and error["message"] == "Internal error"
            assert agnara_code(error) == "internal_failure"
            assert "secret" not in reply.text and "Traceback" not in reply.text

    run(scenario())


def test_tuples_are_projected_as_arrays() -> None:
    async def scenario() -> None:
        async with serve("pair") as (http, _, _state):
            assert result_of(await rpc(http, {"message": message({})})) == [1, 2]

    run(scenario())


def test_the_body_limit_and_the_deadline_are_enforced() -> None:
    async def scenario() -> None:
        async with serve("slow", timeout=0.05, max_body_bytes=256) as (http, _, _state):
            oversized = await http.post("/", content=b"x" * 257)
            assert oversized.status_code == 413
            error = await error_of(http, {"message": message({})})
            assert error["code"] == -32603 and agnara_code(error) == "timeout"

    run(scenario())


def test_other_operations_follow_the_no_task_profile() -> None:
    async def scenario() -> None:
        async with serve("add") as (http, _, _state):
            listed = (await rpc(http, {}, method="ListTasks"))["result"]
            assert listed.get("tasks", []) == []
            for method, params, code in (
                ("GetTask", {"id": "missing"}, -32001),
                ("CancelTask", {"id": "missing"}, -32001),
                ("SendStreamingMessage", {"message": message({"a": 1, "b": 1})}, -32004),
                ("GetExtendedAgentCard", {}, -32004),
                ("ListTaskPushNotificationConfigs", {"taskId": "missing"}, -32003),
            ):
                body = await rpc(http, params, method=method)
                assert body["error"]["code"] == code, (method, body)

    run(scenario())


def test_the_card_is_public_fixed_and_cacheable() -> None:
    async def scenario() -> None:
        async with serve("add", card_cache_control="max-age=60") as (http, _, _state):
            reply = await http.get("/.well-known/agent-card.json", headers={"Authorization": ""})
            assert reply.status_code == 200
            assert reply.headers["cache-control"] == "max-age=60"
            card = reply.json()
            assert card["supportedInterfaces"] == [
                {"url": URL, "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
            ]
            assert card["capabilities"] == {
                "streaming": False,
                "pushNotifications": False,
                "extendedAgentCard": False,
            }
            assert card["skills"] == [
                {"id": "add", "name": "Add", "description": "Runs add", "tags": ["calc"]}
            ]
            assert "securitySchemes" not in card
            cached = await http.get(
                "/.well-known/agent-card.json", headers={"If-None-Match": reply.headers["etag"]}
            )
            assert cached.status_code == 304

    run(scenario())


def test_the_surface_records_one_neutral_exposure() -> None:
    app, _ = build_app()
    a2a = A2a(app, surface="public")
    exposure = a2a.skill(
        definition(app, "add"), id="add", name="Add", description="Adds", tags=("calc",)
    )
    compiled = a2a.compile_surface()

    assert compiled.runtime is exposure and a2a.is_compiled
    (record,) = compiled.exposures
    assert record.surface == a2a.surface and record.capability_id == exposure.definition.id


def test_a_callable_resolves_to_its_declared_capability() -> None:
    app, _ = build_app()
    a2a = A2a(app)
    handler = definition(app, "add").handler

    assert a2a.skill(handler, id="add", name="Add", description="Adds", tags=("x",)).definition is (
        definition(app, "add")
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"id": " "},
        {"name": ""},
        {"description": ""},
        {"tags": ()},
        {"tags": ("",)},
        {"tags": cast(Any, ["calc"])},
    ],
)
def test_missing_public_metadata_fails_composition(fields: dict[str, Any]) -> None:
    app, _ = build_app()
    metadata: dict[str, Any] = {
        "id": "add",
        "name": "Add",
        "description": "Adds",
        "tags": ("calc",),
    }
    metadata |= fields

    with pytest.raises(A2aDefinitionError):
        A2a(app).skill(definition(app, "add"), **metadata)


def test_composition_refusals() -> None:
    app, _ = build_app()
    with pytest.raises(A2aDefinitionError, match="confirmation"):
        expose(app, "guarded")
    with pytest.raises(A2aDefinitionError, match="no skill"):
        A2a(app).compile()
    a2a = A2a(app)
    a2a.skill(definition(app, "add"), id="add", name="Add", description="Adds", tags=("x",))
    with pytest.raises(A2aDefinitionError, match="another surface"):
        a2a.skill(definition(app, "pair"), id="pair", name="Pair", description="P", tags=("x",))
    a2a.compile()
    with pytest.raises(A2aDefinitionError, match="after A2A compilation"):
        a2a.skill(definition(app, "pair"), id="pair", name="Pair", description="P", tags=("x",))
    with pytest.raises(A2aDefinitionError, match="not declared"):
        A2a(app).skill(
            build_app()[0].compile()[definition(app, "add").id],
            id="a",
            name="A",
            description="A",
            tags=("x",),
        )
    with pytest.raises(A2aDefinitionError, match="card name"):
        A2aAgentCard(name="", description="d", version="1")


@pytest.mark.parametrize(
    "options",
    [
        {"url": "/relative"},
        {"challenge": ""},
        {"principals": None},
        {"timeout": 0},
        {"timeout": float("inf")},
        {"timeout": True},
        {"max_body_bytes": 0},
        {"max_body_bytes": 1.5},
        {"plans": []},
    ],
)
def test_invalid_builder_options_fail_composition(options: dict[str, Any]) -> None:
    app, _ = build_app()
    arguments: dict[str, Any] = {
        "card": CARD,
        "url": URL,
        "principals": principals,
        "challenge": CHALLENGE,
    }
    plans = options.pop("plans", plans_of(app))
    arguments |= options

    with pytest.raises(A2aDefinitionError):
        build_a2a_app(expose(app, "add"), plans, DIContainer(DIRegistry()), **arguments)


def test_a_resolver_must_return_a_principal() -> None:
    app, _ = build_app()
    asgi = build_a2a_app(
        expose(app, "add"),
        plans_of(app),
        DIContainer(DIRegistry()),
        card=CARD,
        url=URL,
        principals=lambda scope: cast(Any, "alice"),
        challenge=CHALLENGE,
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=asgi), base_url="http://agent.test"
        ) as http:
            with pytest.raises(TypeError, match="Principal"):
                await http.post("/", content=json.dumps({}).encode(), headers=ALICE)

    run(scenario())
