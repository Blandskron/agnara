"""Serve one A2A surface over JSON-RPC 2.0 with the official SDK (ADR 0098, ADR 0099).

Three pieces sit around the SDK's route factories. An admission gate runs
before the SDK parses anything: it resolves the principal (``401`` without
one), bounds the body and admits only reviewed protocol revisions. A context
builder hands the SDK the resolved principal and the already-admitted
``A2A-Version`` header, and nothing else from the request. A no-task request
handler validates the profile envelope, converts numbers and projects the
canonical outcome that public ``invoke_result`` returns.

The kernel decides every capability outcome. This module never validates
capability input, never evaluates policy and never classifies a failure.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, MutableMapping
from typing import Any

from a2a.server.context import ServerCallContext
from a2a.server.request_handlers import RequestHandler
from a2a.server.request_handlers.response_helpers import build_error_response
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.common import ServerCallContextBuilder
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.types import a2a_pb2
from a2a.utils.errors import (
    A2AError,
    ContentTypeNotSupportedError,
    InternalError,
    InvalidParamsError,
    PushNotificationNotSupportedError,
    TaskNotFoundError,
    UnsupportedOperationError,
    VersionNotSupportedError,
)
from google.protobuf import json_format
from google.protobuf.message import DecodeError
from starlette.requests import Request
from starlette.routing import Router

from agnara import Principal
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

from ._projection import UnrepresentableValue, normalize_input, project_output
from .card import A2aAgentCard
from .exposure import A2aDefinitionError, A2aSkillExposure
from .protocol import A2A_PROTOCOL_VERSION, SUPPORTED_A2A_PROTOCOL_VERSIONS

__all__: list[str] = []

type _Scope = MutableMapping[str, Any]
type _Message = MutableMapping[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]
type _Send = Callable[[_Message], Awaitable[None]]
type _PrincipalResolver = Callable[[Mapping[str, Any]], Principal | None]

#: ADR 0098 D7 defaults. Deployments may lower them; raising them is their risk.
DEFAULT_MAX_BODY_BYTES = 1 << 20
DEFAULT_TIMEOUT = 30.0

_JSON = "application/json"
_PRINCIPAL_KEY = "agnara_a2a.principal"
_REVISION_HEADER = "a2a-version"


class _Disconnected(Exception):
    """The client left before its body was read."""


class _CapabilityFailure(A2AError):
    """A canonical category the SDK dispatcher emits as ``-32603`` / ``UNKNOWN_ERROR``.

    ADR 0098 D6: the category travels in ``ErrorInfo.metadata.agnaraCode``.
    """


def _redacted_internal() -> InternalError:
    return InternalError(
        message="Internal error", data={"agnaraCode": FailureCode.INTERNAL_FAILURE.value}
    )


def _failure_error(failure: Failure) -> A2AError:
    data = {"agnaraCode": failure.code.value}
    match failure.code:
        case FailureCode.INVALID_INPUT:
            return InvalidParamsError(message=failure.message, data=data)
        case FailureCode.INTERNAL_FAILURE:
            return _redacted_internal()
        case FailureCode.INTERACTION_REQUIRED:
            return _CapabilityFailure(message="Interaction required", data=data)
        case _:
            return _CapabilityFailure(message=failure.message, data=data)


def _admit(params: a2a_pb2.SendMessageRequest) -> dict[str, Any]:
    """ADR 0098 D6 protocol rows: refuse recognized out-of-profile fields before invocation."""
    if params.tenant:
        raise InvalidParamsError(message="tenant routing is not supported")
    configuration = params.configuration
    if configuration.HasField("task_push_notification_config"):
        raise PushNotificationNotSupportedError()
    modes = list(configuration.accepted_output_modes)
    if modes and _JSON not in modes:
        raise ContentTypeNotSupportedError()
    message = params.message
    if message.task_id:
        raise TaskNotFoundError()
    if message.context_id:
        raise UnsupportedOperationError(message="contextId is not accepted")
    if message.reference_task_ids or message.extensions:
        raise UnsupportedOperationError()
    if message.role != a2a_pb2.Role.ROLE_USER:
        raise InvalidParamsError(message="role must be ROLE_USER")
    if len(message.parts) != 1:
        raise InvalidParamsError(message="exactly one part is required")
    part = message.parts[0]
    if part.WhichOneof("content") != "data" or part.media_type not in ("", _JSON):
        raise ContentTypeNotSupportedError()
    raw = json_format.MessageToDict(part.data)
    if type(raw) is not dict:
        raise InvalidParamsError(message="data must be a JSON object")
    try:
        return normalize_input(raw)
    except UnrepresentableValue:
        raise InvalidParamsError(
            message="number outside the supported domain",
            data={"agnaraCode": FailureCode.INVALID_INPUT.value},
        ) from None


def _reply(value: Any) -> a2a_pb2.Message:
    """ADR 0098 D4: one agent message carrying ``{"result": value}``."""
    try:
        built = json_format.ParseDict(
            {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_AGENT",
                "parts": [{"data": {"result": project_output(value)}, "mediaType": _JSON}],
            },
            a2a_pb2.Message(),
        )
        # The dispatcher wraps the reply in SendMessageResponse, whose protobuf
        # copy has a lower nesting ceiling than parsing (ADR 0098 D7). Failing
        # there would surface raw exception text, so the wrapper is built here.
        a2a_pb2.SendMessageResponse(message=built)
    except UnrepresentableValue, json_format.ParseError, DecodeError:
        raise _redacted_internal() from None
    return built


class _ProfileHandler(RequestHandler):
    """ADR 0098 D10: no task state, no background work, one fixed plan."""

    def __init__(self, plan: ExecutionPlan, container: DIContainer, timeout: float) -> None:
        self._plan = plan
        self._container = container
        self._timeout = timeout

    async def on_message_send(
        self, params: a2a_pb2.SendMessageRequest, context: ServerCallContext
    ) -> a2a_pb2.Message:
        # ADR 0098 D6: only an A2AError may reach the SDK dispatcher, which
        # answers anything else with its raw ``str(e)``. Cancellation is a
        # BaseException and keeps propagating to the owned invocation.
        try:
            payload = _admit(params)
            invocation_context = ExecutionContext(
                Invocation(
                    self._plan.definition.id,
                    payload,
                    {"transport": "a2a"},
                    deadline=asyncio.get_running_loop().time() + self._timeout,
                ),
                self._container,
                principal=context.state[_PRINCIPAL_KEY],
            )
            outcome = await invoke_result(
                self._plan, invocation_context, input_materializer=materialize_json
            )
            if isinstance(outcome, Success):
                return _reply(outcome.value)
            raise _failure_error(outcome)
        except A2AError:
            raise
        except Exception:
            raise _redacted_internal() from None

    async def on_get_task(self, params: Any, context: ServerCallContext) -> Any:
        raise TaskNotFoundError()

    async def on_cancel_task(self, params: Any, context: ServerCallContext) -> Any:
        raise TaskNotFoundError()

    async def on_list_tasks(self, params: Any, context: ServerCallContext) -> Any:
        return a2a_pb2.ListTasksResponse()

    async def on_message_send_stream(self, params: Any, context: ServerCallContext) -> Any:
        raise UnsupportedOperationError()
        yield  # pragma: no cover - keeps the SDK's async-generator signature

    async def on_subscribe_to_task(self, params: Any, context: ServerCallContext) -> Any:
        raise UnsupportedOperationError()
        yield  # pragma: no cover - keeps the SDK's async-generator signature

    async def on_create_task_push_notification_config(
        self, params: Any, context: ServerCallContext
    ) -> Any:
        raise PushNotificationNotSupportedError()

    async def on_get_task_push_notification_config(
        self, params: Any, context: ServerCallContext
    ) -> Any:
        raise PushNotificationNotSupportedError()

    async def on_list_task_push_notification_configs(
        self, params: Any, context: ServerCallContext
    ) -> Any:
        raise PushNotificationNotSupportedError()

    async def on_delete_task_push_notification_config(
        self, params: Any, context: ServerCallContext
    ) -> Any:
        raise PushNotificationNotSupportedError()

    async def on_get_extended_agent_card(self, params: Any, context: ServerCallContext) -> Any:
        raise UnsupportedOperationError()


class _PrincipalContext(ServerCallContextBuilder):
    """Pass the resolved principal and the admitted revision header, nothing else.

    The SDK's version validator reads ``A2A-Version`` from ``state["headers"]``,
    where its default builder copies every request header, credentials
    included (ADR 0098 D5). The capability context receives none of them.
    """

    def build(self, request: Request) -> ServerCallContext:
        return ServerCallContext(
            state={
                _PRINCIPAL_KEY: request.scope[_PRINCIPAL_KEY],
                "headers": {_REVISION_HEADER: request.headers.get(_REVISION_HEADER, "")},
            }
        )


async def _empty(send: _Send, status: int, headers: list[tuple[bytes, bytes]]) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": b""})


class _AdmissionGate:
    """ADR 0098 D1/D5/D7: authenticate, bound and admit before the SDK parses.

    Only ``POST`` carries JSON-RPC. The public card (``GET``) and lifespan
    events pass straight through.
    """

    __slots__ = ("_app", "_challenge", "_max_body", "_principals")

    def __init__(
        self, app: Router, principals: _PrincipalResolver, challenge: bytes, max_body: int
    ) -> None:
        self._app = app
        self._principals = principals
        self._challenge = challenge
        self._max_body = max_body

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self._app(scope, receive, send)
            return
        principal = self._principals(scope)
        if principal is None:
            await _empty(send, 401, [(b"www-authenticate", self._challenge)])
            return
        if not isinstance(principal, Principal):
            raise TypeError(
                f"A2A principal resolver must return a Principal or None, got "
                f"{type(principal).__name__}"
            )
        try:
            body = await self._read(receive)
        except _Disconnected:
            return
        if body is None:
            await _empty(send, 413, [])
            return
        if not _admitted_revision(scope):
            await _version_refusal(send, body)
            return
        replayed = False

        async def replay() -> _Message:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self._app({**scope, _PRINCIPAL_KEY: principal}, replay, send)

    async def _read(self, receive: _Receive) -> bytes | None:
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


def _admitted_revision(scope: _Scope) -> bool:
    """One header naming a reviewed ``Major.Minor`` exactly (ADR 0098 D1).

    An absent header means revision 0.3 and is refused like any other.
    """
    values = [
        value.decode("latin-1").strip()
        for name, value in scope["headers"]
        if name.lower() == _REVISION_HEADER.encode()
    ]
    return len(values) == 1 and values[0] in SUPPORTED_A2A_PROTOCOL_VERSIONS


async def _version_refusal(send: _Send, body: bytes) -> None:
    request_id: str | int | None = None
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict) and type(parsed.get("id")) in (str, int):
        request_id = parsed["id"]
    payload = json.dumps(build_error_response(request_id, VersionNotSupportedError())).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", _JSON.encode())],
        }
    )
    await send({"type": "http.response.body", "body": payload})


def _timeout_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise A2aDefinitionError(f"A2A timeout must be a number of seconds, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise A2aDefinitionError(f"A2A timeout must be positive and finite, got {value!r}")
    return float(value)


def _body_limit(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise A2aDefinitionError(f"A2A max_body_bytes must be a positive integer, got {value!r}")
    return value


def _plan_for(exposure: A2aSkillExposure, plans: Iterable[ExecutionPlan]) -> ExecutionPlan:
    matches = [plan for plan in plans if plan.definition is exposure.definition]
    if len(matches) != 1:
        raise A2aDefinitionError(
            f"expected exactly one compiled plan for {exposure.definition.id}, got {len(matches)}"
        )
    return matches[0]


def build_a2a_app(
    exposure: A2aSkillExposure,
    plans: Iterable[ExecutionPlan],
    di_container: DIContainer,
    *,
    card: A2aAgentCard,
    url: str,
    principals: _PrincipalResolver,
    challenge: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    card_cache_control: str | None = None,
) -> Callable[[_Scope, _Receive, _Send], Awaitable[None]]:
    """Build the ASGI application serving one A2A surface.

    JSON-RPC is answered at the application root and the public Agent Card at
    ``/.well-known/agent-card.json``; the host mounts the application at
    ``url``, which is published verbatim and never derived from a request.

    ``principals`` maps the authenticated ASGI scope to a `Principal`. It is
    required: return ``None`` to refuse with ``401`` and ``challenge`` as the
    ``WWW-Authenticate`` value, before any body is parsed. An anonymous
    surface returns an explicit anonymous principal.

    The application owns no background work and no task state. The host
    owns ``di_container`` and closes it after this application's lifespan.
    """
    if not isinstance(exposure, A2aSkillExposure):
        raise TypeError(f"exposure must be an A2aSkillExposure, got {type(exposure).__name__}")
    if not isinstance(di_container, DIContainer):
        raise TypeError(f"di_container must be a DIContainer, got {type(di_container).__name__}")
    if not isinstance(card, A2aAgentCard):
        raise TypeError(f"card must be an A2aAgentCard, got {type(card).__name__}")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise A2aDefinitionError(f"A2A url must be an absolute http(s) URL, got {url!r}")
    if not callable(principals):
        raise A2aDefinitionError("A2A principals must be a callable resolver")
    if not isinstance(challenge, str) or not challenge.strip() or not challenge.isascii():
        raise A2aDefinitionError("A2A challenge must be a non-empty ASCII WWW-Authenticate value")
    seconds = _timeout_seconds(timeout)
    limit = _body_limit(max_body_bytes)
    plan = _plan_for(exposure, plans)

    agent_card = json_format.ParseDict(
        {
            "name": card.name,
            "description": card.description,
            "version": card.version,
            "supportedInterfaces": [
                {"url": url, "protocolBinding": "JSONRPC", "protocolVersion": A2A_PROTOCOL_VERSION}
            ],
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "extendedAgentCard": False,
            },
            "defaultInputModes": [_JSON],
            "defaultOutputModes": [_JSON],
            "skills": [
                {
                    "id": exposure.id,
                    "name": exposure.name,
                    "description": exposure.description,
                    "tags": list(exposure.tags),
                }
            ],
        },
        a2a_pb2.AgentCard(),
    )
    router = Router(
        routes=[
            *create_jsonrpc_routes(
                _ProfileHandler(plan, di_container, seconds),
                "/",
                context_builder=_PrincipalContext(),
            ),
            *create_agent_card_routes(agent_card, cache_control=card_cache_control),
        ]
    )
    return _AdmissionGate(router, principals, challenge.encode("ascii"), limit)
