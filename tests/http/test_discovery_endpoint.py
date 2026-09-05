"""E8.6: the authorized machine-readable discovery endpoint."""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

import pytest

from agnara import Agnara
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara.introspection import (
    DiscoveryVisibility,
    IntrospectionSnapshot,
    ScopeVisible,
    describe_app,
    snapshot,
)
from agnara.policy import Principal
from agnara_http._discovery import (
    _compile_discovery,
    _DiscoveryDefinitionError,
    _DiscoveryDispatcher,
    _DiscoveryRoute,
)
from agnara_http._dispatch import _compile_exposures, _HTTPExposure

PATH = "/.well-known/agnara-capabilities"


def built() -> IntrospectionSnapshot:
    app = Agnara("billing")
    registry = DIRegistry()

    @app.capability(scopes={"billing:write"}, description="Refund a captured payment.")
    def refund(payment_id: str) -> str:
        return "refunded"

    @app.capability(description="Report service health.")
    def health() -> str:
        return "ok"

    plans = [ExecutionPlan.compile(app.capabilities[key], registry) for key in app.capabilities]
    return snapshot([describe_app(app, plans, dependencies=registry)], project="billing")


def route(**overrides: Any) -> _DiscoveryRoute:
    arguments: dict[str, Any] = {
        "path": PATH,
        "snapshot": built(),
        "visibility": DiscoveryVisibility.agent_safe(ScopeVisible()),
        "principals": lambda scope: Principal("viewer", scopes={"billing:write"}),
        "challenge": 'Bearer realm="agnara"',
    }
    arguments.update(overrides)
    return _DiscoveryRoute(**arguments)


class Fallback:
    """Records that a path this endpoint does not own was delegated unchanged."""

    def __init__(self) -> None:
        self.paths: list[str] = []

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        self.paths.append(scope["path"])
        await send({"type": "http.response.start", "status": 299, "headers": []})
        await send({"type": "http.response.body", "body": b"fallback", "more_body": False})


def dispatcher(
    declared: _DiscoveryRoute | None = None,
    *exposures: _HTTPExposure,
) -> tuple[_DiscoveryDispatcher, Fallback]:
    fallback = Fallback()
    compiled = _compile_discovery(
        route() if declared is None else declared, _compile_exposures(exposures)
    )
    return _DiscoveryDispatcher(compiled, fallback), fallback


def request(
    served: _DiscoveryDispatcher,
    method: str = "GET",
    path: str = PATH,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, dict[bytes, bytes], bytes]:
    events: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    asyncio.run(
        served(
            {
                "type": "http",
                "method": method,
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": headers or [],
            },
            receive,
            send,
        )
    )
    start = next(event for event in events if event["type"] == "http.response.start")
    body = b"".join(
        event.get("body", b"") for event in events if event["type"] == "http.response.body"
    )
    return start["status"], dict(start["headers"]), body


def document(body: bytes) -> dict[str, Any]:
    return json.loads(body.decode("utf-8"))


# --- explicit configuration ------------------------------------------------


def test_the_discovery_path_has_no_implicit_default() -> None:
    parameter = inspect.signature(_DiscoveryRoute).parameters["path"]
    assert parameter.default is inspect.Parameter.empty


def test_authorization_is_required_unless_the_composer_says_otherwise() -> None:
    parameters = inspect.signature(_DiscoveryRoute).parameters
    assert parameters["allow_anonymous"].default is False
    assert parameters["principals"].default is inspect.Parameter.empty


def test_an_authenticating_endpoint_must_declare_its_challenge() -> None:
    with pytest.raises(_DiscoveryDefinitionError, match="challenge"):
        route(challenge=None)


def test_an_anonymous_endpoint_must_not_declare_a_challenge() -> None:
    with pytest.raises(_DiscoveryDefinitionError, match="never answers 401"):
        route(allow_anonymous=True, challenge='Bearer realm="agnara"')


@pytest.mark.parametrize(
    "cache_control",
    ["public", "public, max-age=60", "private, s-maxage=60", "private, immutable"],
)
def test_a_shared_cacheable_document_is_refused_at_startup(cache_control: str) -> None:
    with pytest.raises(_DiscoveryDefinitionError, match="viewer-specific"):
        route(cache_control=cache_control)


@pytest.mark.parametrize("vary", [(), "Authorization", ("",)])
def test_vary_must_name_at_least_one_header(vary: Any) -> None:
    with pytest.raises(_DiscoveryDefinitionError):
        route(vary=vary)


@pytest.mark.parametrize("path", ["/discovery/{id}", "discovery", ""])
def test_the_discovery_path_must_be_static(path: str) -> None:
    with pytest.raises(_DiscoveryDefinitionError):
        route(path=path)


def test_the_discovery_path_is_reserved_against_capability_routes() -> None:
    app = Agnara("billing")

    @app.capability
    def refund() -> str:
        return "refunded"

    plan = ExecutionPlan.compile(app.capabilities["billing.refund"], DIRegistry())

    with pytest.raises(_DiscoveryDefinitionError, match="conflicts with capability"):
        _compile_discovery(route(), _compile_exposures([_HTTPExposure("GET", PATH, plan)]))


@pytest.mark.parametrize(
    "overrides",
    [
        {"snapshot": "not a snapshot"},
        {"visibility": "not a visibility"},
        {"principals": "not callable"},
        {"allow_anonymous": "yes"},
    ],
)
def test_an_invalid_route_is_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(_DiscoveryDefinitionError):
        route(**overrides)


# --- serving ---------------------------------------------------------------


def test_an_identified_viewer_receives_the_filtered_snapshot() -> None:
    served, fallback = dispatcher()

    status, headers, body = request(served)
    payload = document(body)

    assert status == 200
    assert headers[b"content-type"] == b"application/json"
    assert headers[b"content-length"] == str(len(body)).encode("ascii")
    assert payload["format"] == "agnara-introspection"
    assert payload["filtered"] is True
    assert [item["id"] for item in payload["apps"][0]["capabilities"]] == [
        "billing.refund",
        "billing.health",
    ]
    assert fallback.paths == []


def test_the_document_is_filtered_for_the_requesting_viewer() -> None:
    def resolve(scope: dict[str, Any]) -> Principal | None:
        granted = dict(scope["headers"]).get(b"x-scopes", b"").decode()
        return Principal("viewer", scopes=[item for item in granted.split(",") if item])

    served, _ = dispatcher(route(principals=resolve))

    _, _, scoped = request(served, headers=[(b"x-scopes", b"billing:write")])
    _, _, unscoped = request(served, headers=[(b"x-scopes", b"")])

    def identifiers(body: bytes) -> list[str]:
        return [
            capability["id"] for app in document(body)["apps"] for capability in app["capabilities"]
        ]

    assert identifiers(scoped) == ["billing.refund", "billing.health"]
    assert identifiers(unscoped) == ["billing.health"]


def test_a_viewer_specific_document_is_never_shared_cacheable() -> None:
    served, _ = dispatcher()

    _, headers, _ = request(served)

    assert headers[b"cache-control"] == b"private, no-store"
    assert headers[b"vary"] == b"Authorization"


def test_a_composer_may_relax_the_directive_but_not_share_the_document() -> None:
    served, _ = dispatcher(
        route(cache_control="private, max-age=30", vary=("Authorization", "X-Scopes"))
    )

    _, headers, _ = request(served)

    assert headers[b"cache-control"] == b"private, max-age=30"
    assert headers[b"vary"] == b"Authorization, X-Scopes"


def test_an_unidentified_viewer_is_challenged() -> None:
    served, _ = dispatcher(route(principals=lambda scope: None))

    status, headers, body = request(served)
    payload = document(body)

    assert status == 401
    assert headers[b"www-authenticate"] == b'Bearer realm="agnara"'
    assert payload["code"] == "unauthenticated"
    assert payload["status"] == 401
    assert "apps" not in payload


def test_anonymous_discovery_is_available_only_by_explicit_opt_in() -> None:
    served, _ = dispatcher(
        route(
            principals=lambda scope: None,
            allow_anonymous=True,
            challenge=None,
            visibility=DiscoveryVisibility.identity_only(ScopeVisible()),
        )
    )

    status, headers, body = request(served)

    assert status == 200
    assert b"www-authenticate" not in headers
    # An anonymous viewer holds no scope, so a scoped capability stays hidden.
    assert [
        capability["id"] for app in document(body)["apps"] for capability in app["capabilities"]
    ] == ["billing.health"]


def test_a_resolver_that_raises_fails_closed_without_a_traceback() -> None:
    def explode(scope: dict[str, Any]) -> Principal | None:
        raise RuntimeError("token store unreachable")

    served, _ = dispatcher(route(principals=explode))

    status, _, body = request(served)
    payload = document(body)

    assert status == 500
    assert "token store unreachable" not in body.decode("utf-8")
    assert "Traceback" not in body.decode("utf-8")
    assert "apps" not in payload


def test_a_resolver_returning_something_else_is_not_read_as_anonymous() -> None:
    served, _ = dispatcher(route(principals=lambda scope: "viewer"))

    status, _, body = request(served)

    assert status == 500
    assert "apps" not in document(body)


def test_an_anonymous_endpoint_still_refuses_a_broken_resolver() -> None:
    def explode(scope: dict[str, Any]) -> Principal | None:
        raise RuntimeError("boom")

    served, _ = dispatcher(route(principals=explode, allow_anonymous=True, challenge=None))

    status, _, _ = request(served)

    assert status == 500


def test_a_head_request_returns_the_headers_without_a_body() -> None:
    served, _ = dispatcher()

    get_status, get_headers, get_body = request(served)
    head_status, head_headers, head_body = request(served, method="HEAD")

    assert head_status == get_status == 200
    assert head_headers == get_headers
    assert head_body == b""
    assert get_body


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_another_method_is_refused_with_allow(method: str) -> None:
    served, _ = dispatcher()

    status, headers, body = request(served, method=method)

    assert status == 405
    assert headers[b"allow"] == b"GET, HEAD"
    assert document(body)["code"] == "method_not_allowed"


def test_another_path_is_delegated_unchanged() -> None:
    served, fallback = dispatcher()

    status, _, body = request(served, path="/v1/refunds")

    assert status == 299
    assert body == b"fallback"
    assert fallback.paths == ["/v1/refunds"]


def test_the_served_document_is_byte_identical_for_one_viewer() -> None:
    served, _ = dispatcher()

    first = request(served)[2]
    second = request(served)[2]

    assert first == second
    # Compact and key-sorted, so a client diffing two fetches sees only real
    # changes.
    assert b", " not in first
    assert first == json.dumps(document(first), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def test_seeing_a_capability_publishes_no_runtime_object() -> None:
    served, _ = dispatcher(route(visibility=DiscoveryVisibility.unrestricted(ScopeVisible())))

    _, _, body = request(served)
    text = body.decode("utf-8")

    assert "handler" not in text
    assert "function" not in text
    assert "0x" not in text
