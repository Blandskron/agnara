"""Internal A2A-03 fixture of the ADR 0098 complete-result profile.

Experiment code, not an Agnara adapter or public API. It runs only in this
directory's isolated interpreter, where the SDK is installed; SDK modules are
loaded at runtime so the workspace environment never needs them. Agnara is
used only through governed public imports and decides every capability
outcome: this module validates the protocol envelope, converts numbers and
projects outcomes, nothing else.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import math
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from agnara import Confirmation, Principal
from agnara.di import DIContainer
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    Success,
    invoke_result,
)
from agnara.schema import materialize_json

#: ADR 0098 D3/D4: the integer range a protobuf double carries exactly.
SAFE_INTEGER = 2**53 - 1
#: Defensive nesting bound. ADR 0098 D7: the binding refuses earlier
#: (47 input / 31 output levels with protobuf 7.36.2).
MAX_DEPTH = 64
DEFAULT_MAX_BODY = 1 << 20
DEFAULT_TIMEOUT = 30.0
#: ADR 0098 D1: reviewed revisions, compared as exact ``Major.Minor``.
REVISIONS = frozenset({"1.0"})
JSON = "application/json"
_PRINCIPAL_KEY = "agnara.a2a.principal"
_REVISION = re.compile(r"(\d+)\.(\d+)")


def load_sdk() -> SimpleNamespace:
    """Import the isolated SDK modules this fixture uses."""
    return SimpleNamespace(
        pb=importlib.import_module("a2a.types.a2a_pb2"),
        proto=importlib.import_module("google.protobuf.json_format"),
        handlers=importlib.import_module("a2a.server.request_handlers"),
        helpers=importlib.import_module("a2a.server.request_handlers.response_helpers"),
        context=importlib.import_module("a2a.server.context"),
        common=importlib.import_module("a2a.server.routes.common"),
        routes=importlib.import_module("a2a.server.routes.jsonrpc_routes"),
        cards=importlib.import_module("a2a.server.routes.agent_card_routes"),
        errors=importlib.import_module("a2a.utils.errors"),
        starlette=importlib.import_module("starlette.applications"),
        decode_error=importlib.import_module("google.protobuf.message").DecodeError,
    )


class CompositionError(Exception):
    """The surface cannot be composed under the profile (ADR 0098 D5/D8)."""


@dataclass(frozen=True, slots=True)
class CardMetadata:
    """Explicit public card metadata; nothing falls back to definition text."""

    name: str
    description: str
    version: str
    skill_id: str
    skill_name: str
    skill_description: str
    tags: tuple[str, ...]


class _Disconnected(Exception):
    """Internal signal: the client left before its body was read."""


class _Refused(Exception):
    """Internal signal: a value is outside the profile's numeric/shape domain."""


def normalize_input(value: Any, depth: int = 0) -> Any:
    """ADR 0098 D3: turn protobuf ``Value`` floats back into JSON-shaped input."""
    if depth > MAX_DEPTH:
        raise _Refused
    if value is None or type(value) in (bool, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise _Refused
        if value.is_integer():
            if abs(value) > SAFE_INTEGER:
                raise _Refused
            return int(value)
        return value
    if type(value) is int:
        if abs(value) > SAFE_INTEGER:
            raise _Refused
        return value
    if type(value) is dict:
        return {key: normalize_input(item, depth + 1) for key, item in value.items()}
    if type(value) is list:
        return [normalize_input(item, depth + 1) for item in value]
    raise _Refused


def project_output(value: Any, depth: int = 0) -> Any:
    """ADR 0098 D4: explicit JSON built-ins the binding carries faithfully."""
    if depth > MAX_DEPTH:
        raise _Refused
    if value is None or type(value) in (bool, str):
        return value
    if type(value) is int:
        if abs(value) > SAFE_INTEGER:
            raise _Refused
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise _Refused
        return value
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise _Refused
        return {key: project_output(item, depth + 1) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [project_output(item, depth + 1) for item in value]
    raise _Refused


def _depth(value: Any, depth: int = 0) -> int:
    if depth > MAX_DEPTH:
        return depth
    if isinstance(value, dict):
        return max((_depth(item, depth + 1) for item in value.values()), default=depth)
    if isinstance(value, list):
        return max((_depth(item, depth + 1) for item in value), default=depth)
    return depth


async def _plain(send: Any, status: int, headers: list[tuple[bytes, bytes]]) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": b""})


class AdmissionGate:
    """ADR 0098 D1/D5/D7: authenticate, bound and admit before the SDK parses.

    ``authenticate`` stands in for the host's authentication boundary; it sees
    the Authorization header and returns a verified identity or ``None``.
    ``principal`` is the adapter's required resolver from that identity.
    """

    def __init__(
        self,
        app: Any,
        sdk: SimpleNamespace,
        *,
        rpc_path: str,
        authenticate: Callable[[str | None], str | None],
        principal: Callable[[str], Principal],
        max_body: int = DEFAULT_MAX_BODY,
    ) -> None:
        self._app = app
        self._sdk = sdk
        self._rpc_path = rpc_path
        self._authenticate = authenticate
        self._principal = principal
        self._max_body = max_body

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["path"] != self._rpc_path:
            await self._app(scope, receive, send)
            return
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope["headers"]
        }
        identity = self._authenticate(headers.get("authorization"))
        if identity is None:
            await _plain(send, 401, [(b"www-authenticate", b'Bearer realm="a2a-fixture"')])
            return
        try:
            body = await self._read(receive)
        except _Disconnected:
            return
        if body is None:
            await _plain(send, 413, [])
            return
        revision = _REVISION.fullmatch(headers.get("a2a-version", "").strip())
        if revision is None or f"{revision[1]}.{revision[2]}" not in REVISIONS:
            await self._version_refusal(send, body)
            return
        scope = {**scope, _PRINCIPAL_KEY: self._principal(identity)}
        replayed = False

        async def replay() -> Mapping[str, Any]:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self._app(scope, replay, send)

    async def _read(self, receive: Any) -> bytes | None:
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise _Disconnected
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self._max_body:
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)

    async def _version_refusal(self, send: Any, body: bytes) -> None:
        request_id = None
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and type(parsed.get("id")) in (str, int):
            request_id = parsed["id"]
        error = self._sdk.errors.VersionNotSupportedError()
        payload = json.dumps(self._sdk.helpers.build_error_response(request_id, error)).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": payload})


def build_surface(
    sdk: SimpleNamespace,
    plan: ExecutionPlan,
    container: DIContainer,
    *,
    card: CardMetadata,
    url: str,
    authenticate: Callable[[str | None], str | None],
    principal: Callable[[str], Principal],
    timeout: float = DEFAULT_TIMEOUT,
    max_body: int = DEFAULT_MAX_BODY,
    on_close: Callable[[], Awaitable[None]] | None = None,
) -> SimpleNamespace:
    """Compose one capability as one A2A surface (ADR 0098 D2)."""
    if plan.definition.confirmation is Confirmation.REQUIRED:
        raise CompositionError("capabilities requiring confirmation cannot be served")
    for field_name in ("name", "description", "version", "skill_id", "skill_name"):
        if not getattr(card, field_name).strip():
            raise CompositionError(f"public card metadata {field_name!r} is required")
    if not card.skill_description.strip() or not card.tags:
        raise CompositionError("public skill description and at least one tag are required")
    if timeout <= 0:
        raise CompositionError("an invocation deadline is required")

    pb, proto, errors = sdk.pb, sdk.proto, sdk.errors

    class CapabilityFailure(errors.A2AError):
        """ADR 0098 D6: the SDK emits -32603 / UNKNOWN_ERROR for this type;
        the category travels in ``ErrorInfo.metadata.agnaraCode``."""

    class PrincipalContext(sdk.common.ServerCallContextBuilder):
        """Carry the resolved principal and an allowlisted header set only.

        The SDK's ``validate_version`` reads ``A2A-Version`` from
        ``state["headers"]``, where its default builder copies every request
        header, credentials included. Only that already-admitted header is
        copied here; the capability context receives none of them.
        """

        def build(self, request: Any) -> Any:
            revision = request.headers.get("a2a-version", "")
            return sdk.context.ServerCallContext(
                state={
                    "principal": request.scope[_PRINCIPAL_KEY],
                    "headers": {"a2a-version": revision},
                }
            )

    def failure_error(failure: Failure) -> Exception:
        data = {"agnaraCode": failure.code.value}
        match failure.code:
            case FailureCode.INVALID_INPUT:
                return errors.InvalidParamsError(message=failure.message, data=data)
            case FailureCode.INTERNAL_FAILURE:
                return errors.InternalError(message="Internal error", data=data)
            case FailureCode.INTERACTION_REQUIRED:
                return CapabilityFailure(message="Interaction required", data=data)
            case _:
                return CapabilityFailure(message=failure.message, data=data)

    def admit(params: Any) -> dict[str, Any]:
        """ADR 0098 D6 protocol rows; recognized out-of-profile fields refuse."""
        if params.tenant:
            raise errors.InvalidParamsError(message="tenant routing is not supported")
        configuration = params.configuration
        if configuration.HasField("task_push_notification_config"):
            raise errors.PushNotificationNotSupportedError()
        modes = list(configuration.accepted_output_modes)
        if modes and JSON not in modes:
            raise errors.ContentTypeNotSupportedError()
        message = params.message
        if message.task_id:
            raise errors.TaskNotFoundError()
        if message.context_id:
            raise errors.UnsupportedOperationError(message="contextId is not accepted")
        if message.reference_task_ids or message.extensions:
            raise errors.UnsupportedOperationError()
        if message.role != pb.Role.ROLE_USER:
            raise errors.InvalidParamsError(message="role must be ROLE_USER")
        if len(message.parts) != 1:
            raise errors.InvalidParamsError(message="exactly one part is required")
        part = message.parts[0]
        if part.WhichOneof("content") != "data" or part.media_type not in ("", JSON):
            raise errors.ContentTypeNotSupportedError()
        raw = proto.MessageToDict(part.data)
        if type(raw) is not dict:
            raise errors.InvalidParamsError(message="data must be a JSON object")
        if _depth(raw) > MAX_DEPTH:
            raise errors.InvalidParamsError(message="data is nested too deeply")
        try:
            return normalize_input(raw)
        except _Refused:
            raise errors.InvalidParamsError(
                message="number outside the supported domain",
                data={"agnaraCode": FailureCode.INVALID_INPUT.value},
            ) from None

    def reply(value: Any) -> Any:
        try:
            built = proto.ParseDict(
                {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_AGENT",
                    "parts": [{"data": {"result": project_output(value)}, "mediaType": JSON}],
                },
                pb.Message(),
            )
            # The dispatcher wraps the reply in SendMessageResponse, whose
            # protobuf copy has a lower nesting ceiling than parsing. Failing
            # there would surface the raw exception text, so check it here.
            pb.SendMessageResponse(message=built)
        except _Refused, proto.ParseError, sdk.decode_error:
            raise errors.InternalError(message="Internal error") from None
        return built

    class ProfileHandler(sdk.handlers.RequestHandler):
        """ADR 0098 D10: no task state, no background work."""

        async def on_message_send(self, params: Any, context: Any) -> Any:
            payload = admit(params)
            invocation_context = ExecutionContext(
                Invocation(
                    plan.definition.id,
                    payload,
                    {"transport": "a2a"},
                    deadline=asyncio.get_running_loop().time() + timeout,
                ),
                container,
                principal=context.state["principal"],
            )
            outcome = await invoke_result(
                plan, invocation_context, input_materializer=materialize_json
            )
            if isinstance(outcome, Success):
                return reply(outcome.value)
            raise failure_error(outcome)

        async def on_get_task(self, params: Any, context: Any) -> Any:
            raise errors.TaskNotFoundError()

        async def on_cancel_task(self, params: Any, context: Any) -> Any:
            raise errors.TaskNotFoundError()

        async def on_list_tasks(self, params: Any, context: Any) -> Any:
            return pb.ListTasksResponse()

        async def on_message_send_stream(self, params: Any, context: Any) -> Any:
            raise errors.UnsupportedOperationError()
            yield  # pragma: no cover - preserve the SDK's async-generator signature

        async def on_subscribe_to_task(self, params: Any, context: Any) -> Any:
            raise errors.UnsupportedOperationError()
            yield  # pragma: no cover

        async def on_create_task_push_notification_config(self, params: Any, context: Any) -> Any:
            raise errors.PushNotificationNotSupportedError()

        async def on_get_task_push_notification_config(self, params: Any, context: Any) -> Any:
            raise errors.PushNotificationNotSupportedError()

        async def on_list_task_push_notification_configs(self, params: Any, context: Any) -> Any:
            raise errors.PushNotificationNotSupportedError()

        async def on_delete_task_push_notification_config(self, params: Any, context: Any) -> Any:
            raise errors.PushNotificationNotSupportedError()

        async def on_get_extended_agent_card(self, params: Any, context: Any) -> Any:
            raise errors.UnsupportedOperationError()

    agent_card = proto.ParseDict(
        {
            "name": card.name,
            "description": card.description,
            "version": card.version,
            "supportedInterfaces": [
                {"url": url, "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
            ],
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "extendedAgentCard": False,
            },
            "defaultInputModes": [JSON],
            "defaultOutputModes": [JSON],
            "skills": [
                {
                    "id": card.skill_id,
                    "name": card.skill_name,
                    "description": card.skill_description,
                    "tags": list(card.tags),
                }
            ],
        },
        pb.AgentCard(),
    )

    @asynccontextmanager
    async def lifespan(_: Any) -> Any:
        try:
            yield
        finally:
            if on_close is not None:
                await on_close()

    handler = ProfileHandler()
    inner = sdk.starlette.Starlette(
        routes=sdk.routes.create_jsonrpc_routes(handler, "/rpc", context_builder=PrincipalContext())
        + sdk.cards.create_agent_card_routes(agent_card),
        lifespan=lifespan,
    )
    gate = AdmissionGate(
        inner,
        sdk,
        rpc_path="/rpc",
        authenticate=authenticate,
        principal=principal,
        max_body=max_body,
    )
    return SimpleNamespace(app=gate, inner=inner, card=agent_card, handler=handler)
