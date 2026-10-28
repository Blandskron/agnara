"""A2A-03 probe: drive the ADR 0098 fixture through the official client.

Run from the repository root with this experiment's isolated interpreter:
``experiments/a2a/.venv/Scripts/python.exe -m experiments.a2a.fixture_probe``.
Every row asserts an observation. Rows where the observation differs from
ADR 0098 are recorded under ``deviations`` instead of being hidden.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.metadata
import json
import platform
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from experiments.a2a.fixture import (
    DEFAULT_MAX_BODY,
    MAX_DEPTH,
    CardMetadata,
    CompositionError,
    build_surface,
    load_sdk,
)

from agnara import (
    Agnara,
    CapabilityId,
    ConfirmationEvidence,
    ConfirmationVerdict,
    Principal,
)
from agnara.di import DIContainer, DIRegistry
from agnara.execution import ExecutionContext, ExecutionPlan, Failure, FailureCode, Invocation

URL = "http://fixture.invalid/rpc"
TOKENS = {"Bearer alice-token": "alice", "Bearer bob-token": "bob", "Bearer admin-token": "admin"}
ALICE = {"Authorization": "Bearer alice-token"}
ADMIN = {"Authorization": "Bearer admin-token"}

#: ADR 0098 D6 expectations for canonical outcomes: (JSON-RPC code, reason).
EXPECTED_FAILURES = {
    FailureCode.INVALID_INPUT: (-32602, "INVALID_INPUT"),
    FailureCode.UNAUTHENTICATED: (-32000, "UNAUTHENTICATED"),
    FailureCode.FORBIDDEN: (-32000, "FORBIDDEN"),
    FailureCode.NOT_FOUND: (-32000, "NOT_FOUND"),
    FailureCode.CONFLICT: (-32000, "CONFLICT"),
    FailureCode.RATE_LIMITED: (-32000, "RATE_LIMITED"),
    FailureCode.INTERACTION_REQUIRED: (-32000, "INTERACTION_REQUIRED"),
    FailureCode.UNAVAILABLE: (-32000, "UNAVAILABLE"),
    FailureCode.TIMEOUT: (-32000, "TIMEOUT"),
    FailureCode.INTERNAL_FAILURE: (-32603, "INTERNAL_FAILURE"),
}

CARD = CardMetadata(
    name="Fixture agent",
    description="A2A-03 internal fixture; not an Agnara endpoint",
    version="fixture",
    skill_id="run",
    skill_name="Run",
    skill_description="Runs one composed fixture capability",
    tags=("fixture",),
)


class NeverConfirms:
    """Verifier that the profile must never reach: composition refuses first."""

    async def verify(
        self,
        evidence: ConfirmationEvidence,
        *,
        capability_id: CapabilityId,
        invocation: Invocation,
        principal: Principal,
    ) -> ConfirmationVerdict:
        raise AssertionError("A2A composition must refuse before any verification")


def authenticate(header: str | None) -> str | None:
    """Host authentication stand-in: a fixed token table, never a claim."""
    return TOKENS.get(header or "")


def principal(identity: str) -> Principal:
    scopes = {"fixture:admin"} if identity == "admin" else set()
    return Principal(identity, scopes=scopes)


def build_app() -> tuple[Agnara, dict[str, Any]]:
    app = Agnara("fixture")
    state: dict[str, Any] = {"effects": 0, "cancelled": False, "entered": asyncio.Event()}

    @app.capability(output=int)
    def add(a: int, b: int) -> int:
        return a + b

    @app.capability(output=float)
    def scale(x: float) -> float:
        return x * 2

    @app.capability(output=dict[str, Any])
    def shape() -> dict[str, Any]:
        return {"items": [1, "two", None, True], "nested": {"ok": 1.5}, "empty": None}

    @app.capability(output=int)
    def depth(value: Any) -> int:
        return 0

    @app.capability
    def nest(levels: int) -> Any:
        value: Any = 0
        for _ in range(levels):
            value = {"n": value}
        return value

    @app.capability(output=str)
    def outcome(code: str) -> str | Failure:
        return Failure(FailureCode(code), f"canonical {code} message")

    @app.capability(scopes=("fixture:admin",), output=str)
    def admin_only() -> str:
        state["effects"] += 1
        return "done"

    @app.capability(output=str)
    def explode() -> str:
        raise RuntimeError("secret-token-xyz in /srv/private/path")

    @app.capability(output=int)
    def wrong_output() -> int:
        return cast(int, "not an int")

    @app.capability(output=int)
    def huge() -> int:
        return 2**60

    @app.capability(output=float)
    def not_finite() -> float:
        return float("nan")

    @app.capability(output=str)
    async def slow() -> str:
        await asyncio.sleep(10)
        return "late"

    @app.capability(output=str)
    async def held() -> str:
        state["entered"].set()
        try:
            await asyncio.Event().wait()
        finally:
            state["cancelled"] = True
        return "never"

    @app.capability(output=dict[str, Any])
    async def whoami(context: ExecutionContext, pause: float) -> dict[str, Any]:
        await asyncio.sleep(pause)
        return {
            "identity": context.principal.identity,
            "metadata": dict(context.invocation.metadata),
        }

    @app.capability(confirmation="required", output=str)
    def guarded() -> str:
        return "approved"

    return app, state


async def probe() -> dict[str, Any]:
    assert sys.version_info[:2] == (3, 14)
    assert importlib.metadata.version("a2a-sdk") == "1.3.0"
    sdk = load_sdk()
    httpx = importlib.import_module("httpx")
    rpc = importlib.import_module("a2a.client.transports.jsonrpc")
    pb, proto = sdk.pb, sdk.proto

    app, state = build_app()
    registry = DIRegistry()
    plans = {
        str(cid): ExecutionPlan.compile(d, registry, confirmation_verifier=NeverConfirms())
        for cid, d in app.compile().items()
    }
    container = DIContainer(registry)
    events: list[str] = []
    results: dict[str, Any] = {}
    deviations: list[dict[str, Any]] = []

    @asynccontextmanager
    async def serve(name: str, **options: Any) -> Any:
        async def closed() -> None:
            events.append(f"{name}.lifespan.close")

        surface = build_surface(
            sdk,
            plans[f"fixture.{name}"],
            container,
            card=CARD,
            url=URL,
            authenticate=authenticate,
            principal=principal,
            on_close=closed,
            **options,
        )
        async with surface.inner.router.lifespan_context(surface.inner):
            async with (
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=surface.app),
                    base_url="http://fixture.invalid",
                    headers={"A2A-Version": "1.0", **ALICE},
                ) as http,
                rpc.JsonRpcTransport(http, surface.card, URL, is_shared_httpx=True) as c,
            ):
                yield http, c
            events.append(f"{name}.client.close")

    def message(data: Any, **extra: Any) -> dict[str, Any]:
        body = {"messageId": "client-message", "role": "ROLE_USER", "parts": [{"data": data}]}
        body.update(extra)
        return body

    def send(data: Any, **extra: Any) -> dict[str, Any]:
        return {"message": message(data, **extra)}

    async def raw(http: Any, params: Any, method: str = "SendMessage", **kwargs: Any) -> Any:
        reply = await http.post(
            "/rpc",
            json={"jsonrpc": "2.0", "id": "probe", "method": method, "params": params},
            **kwargs,
        )
        return reply

    async def rpc_error(http: Any, params: Any, method: str = "SendMessage", **kw: Any) -> Any:
        reply = await raw(http, params, method, **kw)
        assert reply.status_code == 200, reply.status_code
        body = reply.json()
        assert "error" in body, body
        return body["error"], reply.text

    def info(error: dict[str, Any]) -> dict[str, Any]:
        details = [item for item in error.get("data", []) if "ErrorInfo" in item.get("@type", "")]
        return details[0] if details else {}

    def refused_by(error: dict[str, Any]) -> str:
        if error["message"] == "data is nested too deeply":
            return "fixture"
        if any("parseError" in item.get("metadata", {}) for item in error.get("data", [])):
            return "sdk-parser"
        return "kernel"

    def result_of(answer: Any) -> Any:
        assert answer.WhichOneof("payload") == "message"
        parsed = proto.MessageToDict(answer.message)
        return parsed, parsed["parts"][0]["data"]["result"]

    async with asyncio.timeout(60):
        # D3/D4: official client round trips with the numeric domain.
        async with serve("add") as (http, client):
            request = proto.ParseDict(
                {"message": message({"a": 2, "b": 3})}, pb.SendMessageRequest()
            )
            parsed, value = result_of(await client.send_message(request))
            assert value == 5
            results["add"] = {"result": value, "client_type": type(value).__name__}
            assert parsed["role"] == "ROLE_AGENT" and parsed["messageId"] != "client-message"
            assert "contextId" not in parsed and "taskId" not in parsed
            assert parsed["parts"][0]["mediaType"] == "application/json"
            results["response_identifiers"] = {
                "fresh_message_id": True,
                "context_id": None,
                "task_id": None,
                "client_accepts_message_without_context_id": True,
            }
            for data, label in (
                ({"a": 2.5, "b": 1}, "fraction"),
                ({"a": 2**53 + 1, "b": 0}, "big"),
            ):
                error, _ = await rpc_error(http, send(data))
                assert error["code"] == -32602, error
                assert info(error)["metadata"] == {"agnaraCode": "invalid_input"}, error
                results[f"add_{label}"] = {
                    "code": error["code"],
                    "reason": info(error).get("reason"),
                    "message": error["message"],
                }
            assert results["add_big"]["message"] == "number outside the supported domain"
            error, _ = await rpc_error(http, send({"a": 9007199254740992, "b": 0}))
            assert error["code"] == -32602
            assert error["message"] == "number outside the supported domain"
            results["add_two_pow_53"] = error["code"]
            ok = await raw(http, send({"a": 9007199254740991, "b": 0}))
            assert "result" in ok.json(), ok.text
            assert ok.json()["result"]["message"]["parts"][0]["data"]["result"] == 2**53 - 1
            results["add_max_safe"] = "accepted"

            # D6 protocol rows: refused before invocation.
            protocol_rows = {
                "taskId": (message({"a": 1, "b": 1}, taskId="t"), -32001),
                "contextId": (message({"a": 1, "b": 1}, contextId="c"), -32004),
                "referenceTaskIds": (message({"a": 1, "b": 1}, referenceTaskIds=["t"]), -32004),
                "extensions": (message({"a": 1, "b": 1}, extensions=["urn:x"]), -32004),
                "role_agent": ({**message({"a": 1, "b": 1}), "role": "ROLE_AGENT"}, -32602),
                "two_parts": (
                    {
                        **message({"a": 1, "b": 1}),
                        "parts": [{"data": {"a": 1}}, {"data": {"b": 1}}],
                    },
                    -32602,
                ),
                "text_part": ({**message({}), "parts": [{"text": "add 1 and 1"}]}, -32005),
                "url_part": (
                    {**message({}), "parts": [{"url": "https://fixture.invalid/x"}]},
                    -32005,
                ),
                "non_json_media_type": (
                    {**message({}), "parts": [{"data": {"a": 1, "b": 1}, "mediaType": "text/csv"}]},
                    -32005,
                ),
                "list_data": (message([1, 2]), -32602),
            }
            results["protocol_rows"] = {}
            for name, (body, code) in protocol_rows.items():
                error, _ = await rpc_error(http, {"message": body})
                assert error["code"] == code, (name, error)
                # Guard against a row passing for an unrelated refusal.
                assert name == "role_agent" or "role must" not in error["message"], (name, error)
                results["protocol_rows"][name] = code
            for name, params, code in (
                ("tenant", {"tenant": "other", "message": message({"a": 1, "b": 1})}, -32602),
                (
                    "push_config",
                    {
                        "message": message({"a": 1, "b": 1}),
                        "configuration": {
                            "taskPushNotificationConfig": {"url": "https://fixture.invalid/p"}
                        },
                    },
                    -32003,
                ),
                (
                    "output_mode",
                    {
                        "message": message({"a": 1, "b": 1}),
                        "configuration": {"acceptedOutputModes": ["text/plain"]},
                    },
                    -32005,
                ),
            ):
                error, _ = await rpc_error(http, params)
                assert error["code"] == code, (name, error)
                results["protocol_rows"][name] = code
            # D2: unrecognized fields are ignored; ignored configuration has no effect.
            tolerant = {
                "message": {**message({"a": 4, "b": 4}), "capabilityId": "fixture.explode"},
                "configuration": {"historyLength": 3, "returnImmediately": True},
                "metadata": {"capability": "fixture.explode"},
                "skillId": "explode",
            }
            reply = await raw(http, tolerant)
            assert reply.json()["result"]["message"]["parts"][0]["data"]["result"] == 8
            results["unknown_fields_ignored"] = True

            # D1: revision admission before the SDK.
            results["versions"] = {}
            for revision in ("", "0.3", "1.99", "9.0", "1.0.0"):
                error, _ = await rpc_error(
                    http, send({"a": 1, "b": 1}), headers={"A2A-Version": revision}
                )
                assert error["code"] == -32009, (revision, error)
                results["versions"][revision or "empty"] = -32009
            results["versions"]["1.0"] = "accepted"

            # D5: host authentication before body parsing.
            unauthenticated = await http.post(
                "/rpc", content=b"{not json", headers={"Authorization": ""}
            )
            assert unauthenticated.status_code == 401
            assert unauthenticated.headers["www-authenticate"].startswith("Bearer")
            forged = await raw(http, send({"a": 1, "b": 1}), headers={"Authorization": "Bearer x"})
            assert forged.status_code == 401
            results["authentication"] = {"missing": 401, "unknown_token": 401, "challenge": True}

            # D6 JSON-RPC rows owned by the SDK.
            parse = await http.post("/rpc", content=b"{not json")
            assert parse.json()["error"]["code"] == -32700
            error, _ = await rpc_error(http, {}, method="NoSuchMethod")
            assert error["code"] == -32601
            results["jsonrpc"] = {"parse": -32700, "unknown_method": -32601}

            # D6 other operations.
            listed = (await raw(http, {}, method="ListTasks")).json()["result"]
            assert listed["tasks"] == [] and listed["nextPageToken"] == ""
            operations = {
                "GetTask": ({"id": "missing"}, -32001),
                "CancelTask": ({"id": "missing"}, -32001),
                "SendStreamingMessage": ({"message": message({"a": 1, "b": 1})}, -32004),
                "SubscribeToTask": ({"id": "missing"}, -32004),
                "CreateTaskPushNotificationConfig": (
                    {"taskId": "missing", "url": "https://fixture.invalid/p"},
                    -32003,
                ),
                "GetTaskPushNotificationConfig": ({"taskId": "missing", "id": "x"}, -32003),
                "ListTaskPushNotificationConfigs": ({"taskId": "missing"}, -32003),
                "DeleteTaskPushNotificationConfig": ({"taskId": "missing", "id": "x"}, -32003),
                "GetExtendedAgentCard": ({}, -32004),
            }
            observed_operations: dict[str, object] = {"ListTasks": "empty"}
            results["operations"] = observed_operations
            for method, (params, code) in operations.items():
                error, _ = await rpc_error(http, params, method=method)
                assert error["code"] == code, (method, error)
                observed_operations[method] = code

            # D8: public card.
            discovered = await http.get("/.well-known/agent-card.json")
            card = discovered.json()
            assert card["capabilities"] == {
                "streaming": False,
                "pushNotifications": False,
                "extendedAgentCard": False,
            }
            assert card["supportedInterfaces"] == [
                {"url": URL, "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
            ]
            assert card["defaultInputModes"] == card["defaultOutputModes"] == ["application/json"]
            assert "securitySchemes" not in card
            cached = await http.get(
                "/.well-known/agent-card.json",
                headers={"If-None-Match": discovered.headers["etag"]},
            )
            assert cached.status_code == 304
            results["card"] = {
                "flags_false": True,
                "single_interface": True,
                "etag_304": True,
                "cache_control": discovered.headers.get("cache-control"),
            }

        async with serve("add", max_body=4096) as (http, client):
            big = await raw(http, send({"a": 1, "b": 1, "pad": "x" * 8192}))
            assert big.status_code == 413
            results["body_limit"] = {"configured": 4096, "status": 413}
        results["default_max_body"] = DEFAULT_MAX_BODY

        async with serve("depth") as (http, client):
            # D7 depth: measure where nesting is first refused, and by whom.
            deepest_accepted = 0
            refusal: dict[str, Any] = {}
            for levels in range(1, MAX_DEPTH + 2):
                nested: Any = 0
                for _ in range(levels):
                    nested = {"n": nested}
                reply = (await raw(http, send({"value": nested}))).json()
                if "result" in reply:
                    deepest_accepted = levels
                    continue
                error = reply["error"]
                assert error["code"] == -32602, error
                refusal = {
                    "levels": levels,
                    "code": error["code"],
                    "by": refused_by(error),
                    "message": error["message"],
                }
                break
            assert refusal, "nesting beyond the limit must be refused"
            results["depth"] = {"deepest_accepted": deepest_accepted, "first_refusal": refusal}
            if deepest_accepted < MAX_DEPTH:
                deviations.append(
                    {
                        "row": "D7 depth",
                        "expected": {"deepest_accepted": MAX_DEPTH},
                        "observed": results["depth"],
                    }
                )

        async with serve("nest") as (http, client):
            deepest_output = 0
            output_refusal: dict[str, Any] = {}
            for levels in range(1, MAX_DEPTH + 2):
                reply = (await raw(http, send({"levels": levels}))).json()
                if "result" in reply:
                    deepest_output = levels
                    continue
                error = reply["error"]
                assert error["code"] == -32603 and error["message"] == "Internal error", error
                output_refusal = {"levels": levels, "code": error["code"], "redacted": True}
                break
            assert output_refusal, "an output beyond the binding's ceiling must be refused"
            results["output_depth"] = {
                "deepest_accepted": deepest_output,
                "first_refusal": output_refusal,
                "after_handler_effects": True,
            }
            if deepest_output < MAX_DEPTH:
                deviations.append(
                    {
                        "row": "D7 output depth",
                        "expected": {"deepest_accepted": MAX_DEPTH},
                        "observed": results["output_depth"],
                    }
                )

        async with serve("scale") as (http, client):
            reply = await raw(http, send({"x": 3}))
            assert reply.json()["result"]["message"]["parts"][0]["data"]["result"] == 6
            results["scale_int_to_float"] = "accepted"

        async with serve("shape") as (http, client):
            request = proto.ParseDict({"message": message({})}, pb.SendMessageRequest())
            _, value = result_of(await client.send_message(request))
            assert value == {"items": [1, "two", None, True], "nested": {"ok": 1.5}, "empty": None}
            results["shape_roundtrip"] = True

        # D6 canonical outcomes, decided by the kernel.
        results["failures"] = {}
        async with serve("outcome") as (http, client):
            for code, expected in EXPECTED_FAILURES.items():
                error, text = await rpc_error(http, send({"code": code.value}))
                detail = info(error)
                observed = {
                    "code": error["code"],
                    "message": error["message"],
                    "reason": detail.get("reason"),
                    "domain": detail.get("domain"),
                    "metadata": detail.get("metadata"),
                }
                results["failures"][code.value] = observed
                assert detail.get("metadata", {}).get("agnaraCode") == code.value, observed
                if (error["code"], detail.get("reason")) != expected:
                    deviations.append(
                        {
                            "row": f"D6 {code.value}",
                            "expected": {"code": expected[0], "reason": expected[1]},
                            "observed": {"code": error["code"], "reason": detail.get("reason")},
                        }
                    )
                if code is FailureCode.INTERACTION_REQUIRED:
                    assert error["message"] == "Interaction required"

        async with serve("admin_only") as (http, client):
            error, _ = await rpc_error(http, send({}))
            assert state["effects"] == 0, "policy must run before handler effects"
            ok = await raw(http, send({}), headers=ADMIN)
            assert ok.json()["result"]["message"]["parts"][0]["data"]["result"] == "done"
            assert state["effects"] == 1
            results["policy_before_effects"] = {
                "denied_code": info(error).get("metadata", {}).get("agnaraCode"),
                "effects_after_denial": 0,
                "effects_after_admin": 1,
            }

        for name in ("explode", "wrong_output", "huge", "not_finite"):
            async with serve(name) as (http, client):
                error, text = await rpc_error(http, send({}))
                assert error["code"] == -32603 and error["message"] == "Internal error", error
                assert "secret-token-xyz" not in text and "/srv/private" not in text
                assert "not an int" not in text
                results[f"redacted_{name}"] = -32603

        async with serve("slow", timeout=0.2) as (http, client):
            error, _ = await rpc_error(http, send({}))
            results["deadline"] = {
                "code": error["code"],
                "agnaraCode": info(error).get("metadata", {}).get("agnaraCode"),
            }
            assert results["deadline"]["agnaraCode"] == "timeout"

        async with serve("whoami") as (http, client):
            bob = {"Authorization": "Bearer bob-token", "X-Forwarded-User": "admin"}
            first, second = await asyncio.gather(
                raw(http, send({"pause": 0.05})),
                raw(http, send({"pause": 0.0}), headers=bob),
            )
            seen = [
                reply.json()["result"]["message"]["parts"][0]["data"]["result"]
                for reply in (first, second)
            ]
            assert [item["identity"] for item in seen] == ["alice", "bob"]
            assert all(item["metadata"] == {"transport": "a2a"} for item in seen)
            results["principal_isolation"] = {
                "concurrent_identities": ["alice", "bob"],
                "context_metadata": {"transport": "a2a"},
                "headers_in_context": False,
            }

        async with serve("held") as (http, client):
            request = proto.ParseDict({"message": message({})}, pb.SendMessageRequest())
            async with asyncio.TaskGroup() as owned:
                pending = owned.create_task(client.send_message(request))
                await state["entered"].wait()
                pending.cancel()
            assert pending.cancelled() and state["cancelled"]
            results["cancellation_reaches_handler"] = True

        results["composition"] = {}
        try:
            build_surface(
                sdk,
                plans["fixture.guarded"],
                container,
                card=CARD,
                url=URL,
                authenticate=authenticate,
                principal=principal,
            )
        except CompositionError:
            results["composition"]["confirmation_required"] = "refused"
        else:
            raise AssertionError("confirmation-required capability must be refused")
        try:
            build_surface(
                sdk,
                plans["fixture.add"],
                container,
                card=_blank_description(),
                url=URL,
                authenticate=authenticate,
                principal=principal,
            )
        except CompositionError:
            results["composition"]["missing_card_metadata"] = "refused"
        else:
            raise AssertionError("missing public metadata must be refused")

    await container.aclose()
    events.append("container.close")
    assert asyncio.all_tasks() == {asyncio.current_task()}
    assert events[-1] == "container.close"
    assert all(
        events[index].endswith("client.close") and events[index + 1].endswith("lifespan.close")
        for index in range(0, len(events) - 1, 2)
    ), events
    results["lifecycle"] = {
        "order_per_surface": ["client.close", "lifespan.close"],
        "final": "container.close",
    }
    results["no_remaining_tasks"] = True
    return {"observations": results, "deviations": deviations}


def _blank_description() -> CardMetadata:
    return CardMetadata(
        name=CARD.name,
        description=" ",
        version=CARD.version,
        skill_id=CARD.skill_id,
        skill_name=CARD.skill_name,
        skill_description=CARD.skill_description,
        tags=CARD.tags,
    )


def main() -> None:
    here = Path(__file__).resolve().parent
    outcome = asyncio.run(probe())
    evidence = {
        "schema_version": 1,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "gil_enabled": sys._is_gil_enabled(),
        "sdk": importlib.metadata.version("a2a-sdk"),
        "agnara": importlib.metadata.version("agnara"),
        "sources_sha256": {
            name: hashlib.sha256((here / name).read_bytes()).hexdigest()
            for name in ("fixture.py", "fixture_probe.py", "requirements.lock")
        },
        **outcome,
    }
    print(json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
