"""SDK-only A2A-01 probes; run with this experiment's isolated interpreter.

No Agnara adapter or public API is implemented. Imports are loaded at runtime
because SDK dependencies intentionally do not belong to the workspace env.
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
from typing import Any


async def probe() -> dict[str, Any]:
    assert sys.version_info[:2] == (3, 14)
    assert importlib.metadata.version("a2a-sdk") == "1.3.0"
    pb = importlib.import_module("a2a.types.a2a_pb2")
    proto = importlib.import_module("google.protobuf.json_format")
    handlers = importlib.import_module("a2a.server.request_handlers")
    executions = importlib.import_module("a2a.server.agent_execution")
    tasks = importlib.import_module("a2a.server.tasks")
    routes = importlib.import_module("a2a.server.routes.jsonrpc_routes")
    cards = importlib.import_module("a2a.server.routes.agent_card_routes")
    rpc = importlib.import_module("a2a.client.transports.jsonrpc")
    errors = importlib.import_module("a2a.utils.errors")
    httpx = importlib.import_module("httpx")
    starlette = importlib.import_module("starlette.applications")

    def parse(value, cls):
        return proto.ParseDict(value, cls())

    def response(value):
        return parse(
            {"messageId": "reply", "role": "ROLE_AGENT", "parts": [{"data": {"result": value}}]},
            pb.Message,
        )

    def request(value):
        return parse(
            {"message": {"messageId": "input", "role": "ROLE_USER", "parts": [{"data": value}]}},
            pb.SendMessageRequest,
        )

    card = parse(
        {
            "name": "SDK feasibility fixture",
            "description": "SDK-only probe, not an Agnara endpoint",
            "version": "probe",
            "supportedInterfaces": [
                {
                    "url": "http://fixture.invalid/rpc",
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": "1.0",
                }
            ],
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "extendedAgentCard": False,
            },
            "defaultInputModes": ["application/json"],
            "defaultOutputModes": ["application/json"],
            "skills": [
                {"id": "echo", "name": "Echo", "description": "Echo fixture", "tags": ["probe"]}
            ],
        },
        pb.AgentCard,
    )
    entries = []
    seen = []
    entered = asyncio.Event()
    mode = "normal"

    class ImmediateHandler(handlers.RequestHandler):
        async def on_message_send(self, params, context):
            seen.append(
                {
                    "authenticated": context.user.is_authenticated,
                    "authorization_in_sdk_state": "authorization"
                    in context.state.get("headers", {}),
                }
            )
            if mode == "cancel":
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    entries.append("cancelled_handler_exit")
            message = proto.MessageToDict(params.message)
            parts = message.get("parts", [])
            if len(parts) != 1 or "data" not in parts[0]:
                raise errors.InvalidParamsError(message="fixture accepts one structured part")
            return response(parts[0]["data"])

        async def on_get_task(self, params, context):
            return None

        async def on_cancel_task(self, params, context):
            return None

        async def on_list_tasks(self, params, context):
            return pb.ListTasksResponse()

        async def on_message_send_stream(self, params, context):
            raise errors.UnsupportedOperationError()
            yield  # pragma: no cover - preserve the SDK's async-generator signature

        async def on_subscribe_to_task(self, params, context):
            raise errors.UnsupportedOperationError()
            yield  # pragma: no cover

        async def on_create_task_push_notification_config(self, params, context):
            raise errors.PushNotificationNotSupportedError()

        async def on_get_task_push_notification_config(self, params, context):
            raise errors.PushNotificationNotSupportedError()

        async def on_list_task_push_notification_configs(self, params, context):
            raise errors.PushNotificationNotSupportedError()

        async def on_delete_task_push_notification_config(self, params, context):
            raise errors.PushNotificationNotSupportedError()

        async def on_get_extended_agent_card(self, params, context):
            raise errors.UnsupportedOperationError()

        async def aclose(self):
            entries.append("handler.close")

    class EchoExecutor(executions.AgentExecutor):
        async def execute(self, context, event_queue):
            message = proto.MessageToDict(context.message)
            await event_queue.enqueue_event(response(message["parts"][0]["data"]))

        async def cancel(self, context, event_queue):
            raise errors.UnsupportedOperationError()

    @asynccontextmanager
    async def serve(handler):
        @asynccontextmanager
        async def lifespan(_):
            entries.append("startup")
            try:
                yield
            finally:
                await handler.aclose()
                entries.append("shutdown")

        app = starlette.Starlette(
            routes=routes.create_jsonrpc_routes(handler, "/rpc")
            + cards.create_agent_card_routes(card),
            lifespan=lifespan,
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://fixture.invalid",
                headers={"A2A-Version": "1.0"},
            ) as http:
                async with rpc.JsonRpcTransport(
                    http, card, "http://fixture.invalid/rpc", is_shared_httpx=True
                ) as client:
                    yield http, client
                assert not http.is_closed
            assert http.is_closed
            entries.append("client.close")

    results: dict[str, Any] = {}
    async with asyncio.timeout(15), serve(ImmediateHandler()) as (http, client):
        values = [7, {"nested": [1, True, None]}, [1, 2], None]
        for value in values:
            answer = await client.send_message(request(value))
            assert answer.WhichOneof("payload") == "message"
            actual = proto.MessageToDict(answer.message)["parts"][0]["data"]["result"]
            assert actual == value, (actual, value)
        results["official_client_roundtrips"] = len(values)

        async def raw(http, method, params, **kwargs):
            reply = await http.post(
                "/rpc",
                json={"jsonrpc": "2.0", "id": "probe", "method": method, "params": params},
                **kwargs,
            )
            assert reply.status_code == 200
            return reply.json()

        empty = await raw(http, "ListTasks", {})
        assert empty["result"]["tasks"] == [] and empty["result"]["nextPageToken"] == ""
        results["no_tasks"] = empty["result"]
        failure_cases = [
            ("GetTask", {"id": "missing"}, -32001),
            ("CancelTask", {"id": "missing"}, -32001),
            ("SendStreamingMessage", proto.MessageToDict(request(1)), -32004),
            ("SubscribeToTask", {"id": "missing"}, -32004),
            (
                "CreateTaskPushNotificationConfig",
                {"taskId": "missing", "url": "https://fixture.invalid/push"},
                -32003,
            ),
            ("GetTaskPushNotificationConfig", {"taskId": "missing", "id": "missing"}, -32003),
            ("ListTaskPushNotificationConfigs", {"taskId": "missing"}, -32003),
            ("DeleteTaskPushNotificationConfig", {"taskId": "missing", "id": "missing"}, -32003),
            ("GetExtendedAgentCard", {}, -32004),
            ("UnknownMethod", {}, -32601),
        ]
        results["operation_errors"] = {}
        for method, params, code in failure_cases:
            reply = await raw(http, method, params)
            assert reply["error"]["code"] == code, (method, reply)
            results["operation_errors"][method] = code

        unknown = proto.MessageToDict(request({"value": 1}))
        unknown["capabilityId"] = "unselected"
        before = len(seen)
        reply = await raw(
            http, "SendMessage", unknown, headers={"Authorization": "Bearer synthetic-probe"}
        )
        assert "result" in reply and len(seen) == before + 1
        assert seen[-1] == {"authenticated": False, "authorization_in_sdk_state": True}
        results["unknown_selector_ignored"] = True
        results["unauthenticated_dispatch"] = seen[-1]

        huge = 2**53 + 1
        raw_large = {
            "message": {
                "messageId": "large",
                "role": "ROLE_USER",
                "parts": [{"data": {"value": huge}}],
            }
        }
        reply = await raw(http, "SendMessage", raw_large)
        rounded = reply["result"]["message"]["parts"][0]["data"]["result"]["value"]
        assert rounded != huge and rounded == 2**53
        results["integer_precision"] = {"sent": huge, "received": rounded}

        results["versions"] = {}
        for revision in ("", "9.0", "1.99"):
            before = len(seen)
            reply = await raw(
                http,
                "SendMessage",
                proto.MessageToDict(request(1)),
                headers={"A2A-Version": revision},
            )
            if revision == "1.99":
                assert "result" in reply and len(seen) == before + 1
                results["versions"][revision] = "accepted"
            else:
                assert reply["error"]["code"] == -32009 and len(seen) == before
                results["versions"][revision or "empty"] = -32009

        discovered = await http.get("/.well-known/agent-card.json")
        assert discovered.status_code == 200 and "etag" in discovered.headers
        cached = await http.get(
            "/.well-known/agent-card.json", headers={"If-None-Match": discovered.headers["etag"]}
        )
        assert cached.status_code == 304
        results["card"] = {
            "etag": True,
            "conditional_status": 304,
            "cache_control": discovered.headers.get("cache-control"),
        }

        mode = "cancel"
        async with asyncio.TaskGroup() as owned:
            pending = owned.create_task(client.send_message(request(1)))
            await entered.wait()
            pending.cancel()
        assert pending.cancelled() and "cancelled_handler_exit" in entries
    assert entries[-3:] == ["client.close", "handler.close", "shutdown"]
    assert asyncio.all_tasks() == {asyncio.current_task()}
    results["immediate_lifecycle"] = entries.copy()

    mode = "normal"
    handler = handlers.DefaultRequestHandler(EchoExecutor(), tasks.InMemoryTaskStore(), card)
    async with asyncio.timeout(15), serve(handler) as (http, client):
        before = await client.list_tasks(pb.ListTasksRequest())
        answer = await client.send_message(request({"value": 3}))
        after = await client.list_tasks(pb.ListTasksRequest())
        assert answer.WhichOneof("payload") == "message"
        default_result: dict[str, Any] = {
            "reply_kind": "message",
            "tasks_before": len(before.tasks),
            "tasks_after": len(after.tasks),
        }
        operation_errors: dict[str, int] = {}
        for method, params, code in failure_cases:
            reply = await raw(http, method, params)
            assert reply["error"]["code"] == code, (method, reply)
            operation_errors[method] = code
        default_result["operation_errors"] = operation_errors
        for name, params in (
            ("get_task", pb.GetTaskRequest(id="missing")),
            ("cancel_task", pb.CancelTaskRequest(id="missing")),
        ):
            try:
                await getattr(client, name)(params)
            except errors.TaskNotFoundError:
                default_result[name] = "TaskNotFoundError"
            else:
                raise AssertionError(f"{name} must refuse an absent task")
        results["default_handler"] = default_result
    assert asyncio.all_tasks() == {asyncio.current_task()}
    results["no_remaining_tasks"] = True
    return results


def main() -> None:
    here = Path(__file__).resolve().parent
    dispatcher_file = importlib.import_module("a2a.server.routes.jsonrpc_dispatcher").__file__
    assert dispatcher_file is not None
    sdk_root = Path(dispatcher_file).resolve().parents[2]
    inspected = (
        "server/routes/jsonrpc_dispatcher.py",
        "server/routes/common.py",
        "server/request_handlers/default_request_handler_v2.py",
        "utils/version_validator.py",
    )
    evidence = {
        "schema_version": 1,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "gil_enabled": sys._is_gil_enabled(),
        "sdk": "1.3.0",
        "sdk_source_sha256": {
            name: hashlib.sha256((sdk_root / name).read_bytes()).hexdigest() for name in inspected
        },
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "requirements_sha256": hashlib.sha256(
            (here / "requirements.lock").read_bytes()
        ).hexdigest(),
        "dependencies": {
            item.metadata["Name"]: item.version
            for item in sorted(
                importlib.metadata.distributions(), key=lambda item: item.metadata["Name"]
            )
        },
        "observations": asyncio.run(probe()),
    }
    print(json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
