"""E8.8: the read-only Agnara Explorer shell."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import pytest

from agnara import Agnara, Confirmation, Risk
from agnara.core.di import DIRegistry, Scope, provider
from agnara.execution import ExecutionPlan
from agnara.introspection import (
    DiscoveryVisibility,
    ExposureDescriptor,
    Hiding,
    IntrospectionSnapshot,
    ScopeVisible,
    describe_app,
    snapshot,
)
from agnara.policy import Principal
from agnara_http._discovery import _DiscoveryDefinitionError
from agnara_http._dispatch import _compile_exposures, _HTTPExposure
from agnara_http._explorer import (
    _compile_explorer,
    _ExplorerDispatcher,
    _ExplorerRoute,
)

BASE = "/explorer"

#: A payload in every field an application controls. If any of them reaches the
#: page unescaped, the marker appears as markup rather than as text.
XSS = "<script>alert('x')</script>"


class Ledger:
    pass


def built(*, hostile: bool = False) -> IntrospectionSnapshot:
    app = Agnara("billing")
    registry = DIRegistry()

    @provider(scope=Scope.SINGLETON)
    def ledger() -> Ledger:
        return Ledger()

    registry.bind(Ledger, ledger)

    description = XSS if hostile else "Refund a captured payment."

    @app.capability(
        description=description,
        scopes={"billing:write"},
        effects={XSS if hostile else "financial-write"},
        risk=Risk.HIGH,
        confirmation=Confirmation.NEVER,
        idempotent=False,
    )
    def refund(payment_id: str, ledger: Ledger) -> str:
        return "refunded"

    @app.capability(description="Report service health.")
    def health() -> str:
        return "ok"

    plans = [ExecutionPlan.compile(app.capabilities[key], registry) for key in app.capabilities]
    exposure_name = XSS if hostile else "POST /refunds"
    return snapshot(
        [
            describe_app(
                app,
                plans,
                dependencies=registry,
                exposures={
                    "billing.refund": [
                        ExposureDescriptor.of("http", exposure_name),
                        ExposureDescriptor.of("mcp", "billing.refund"),
                    ]
                },
            )
        ],
        project=XSS if hostile else "billing",
    )


def route(**overrides: Any) -> _ExplorerRoute:
    arguments: dict[str, Any] = {
        "base_path": BASE,
        "snapshot": built(),
        "visibility": DiscoveryVisibility.unrestricted(ScopeVisible()),
        "principals": lambda scope: Principal("viewer", scopes={"billing:write"}),
        "challenge": "Bearer",
    }
    arguments.update(overrides)
    return _ExplorerRoute(**arguments)


class Fallback:
    def __init__(self) -> None:
        self.paths: list[str] = []

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        self.paths.append(scope["path"])
        await send({"type": "http.response.start", "status": 299, "headers": []})
        await send({"type": "http.response.body", "body": b"fallback", "more_body": False})


def dispatcher(
    declared: _ExplorerRoute | None = None,
    *exposures: _HTTPExposure,
) -> tuple[_ExplorerDispatcher, Fallback]:
    fallback = Fallback()
    compiled = _compile_explorer(
        route() if declared is None else declared, _compile_exposures(exposures)
    )
    return _ExplorerDispatcher(compiled, fallback), fallback


def request(
    served: _ExplorerDispatcher,
    path: str = BASE,
    method: str = "GET",
) -> tuple[int, dict[bytes, bytes], str]:
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
                "headers": [],
            },
            receive,
            send,
        )
    )
    start = next(event for event in events if event["type"] == "http.response.start")
    body = b"".join(
        event.get("body", b"") for event in events if event["type"] == "http.response.body"
    )
    return start["status"], dict(start["headers"]), body.decode("utf-8")


# --- configuration ---------------------------------------------------------


@pytest.mark.parametrize("base_path", ["explorer", "/explorer/", "/explorer/{id}", ""])
def test_the_base_path_must_be_a_static_absolute_path(base_path: str) -> None:
    with pytest.raises(_DiscoveryDefinitionError):
        route(base_path=base_path)


def test_the_explorer_reserves_its_whole_subtree_not_just_its_root() -> None:
    app = Agnara("billing")

    @app.capability
    def nested() -> str:
        return "nested"

    plan = ExecutionPlan.compile(app.capabilities["billing.nested"], DIRegistry())

    with pytest.raises(_DiscoveryDefinitionError, match="would shadow capability route"):
        _compile_explorer(
            route(), _compile_exposures([_HTTPExposure("GET", f"{BASE}/anything", plan)])
        )


def test_the_explorer_shares_the_discovery_authorization_rules_at_compile_time() -> None:
    """The rules live in one place, so they are enforced where that place runs.

    `_ExplorerRoute` validates only what is its own — the base path. Everything
    about authorization and caching is delegated to `_DiscoveryRoute`, which is
    constructed during compilation, so that is where a bad configuration fails.
    """
    empty = _compile_exposures(())

    with pytest.raises(_DiscoveryDefinitionError, match="challenge"):
        _compile_explorer(route(challenge=None), empty)
    with pytest.raises(_DiscoveryDefinitionError, match="viewer-specific"):
        _compile_explorer(route(cache_control="public, max-age=60"), empty)
    with pytest.raises(_DiscoveryDefinitionError, match="never answers 401"):
        _compile_explorer(route(allow_anonymous=True, challenge="Bearer"), empty)


# --- the index -------------------------------------------------------------


def test_the_index_lists_every_visible_capability_with_a_deep_link() -> None:
    served, fallback = dispatcher()

    status, headers, body = request(served)

    assert status == 200
    assert headers[b"content-type"] == b"text/html; charset=utf-8"
    assert "<h1>Agnara Explorer</h1>" in body
    assert f'<a href="{BASE}/app/billing">Application billing</a>' in body
    assert f'<a href="{BASE}/billing.refund">billing.refund</a>' in body
    assert f'<a href="{BASE}/billing.health">billing.health</a>' in body
    assert fallback.paths == []


def test_the_index_shows_non_http_transport_availability() -> None:
    served, _ = dispatcher()

    _, _, body = request(served)

    # The reason this is not an OpenAPI viewer: MCP is a transport OpenAPI
    # cannot describe.
    assert "Transport availability: http, mcp" in body
    assert "billing.refund</a> — http, mcp" in body


def test_the_index_carries_the_snapshot_provenance() -> None:
    served, _ = dispatcher()

    _, _, body = request(served)

    assert "agnara-introspection version 0" in body
    assert "project billing" in body


def test_every_page_says_that_seeing_is_not_authorization() -> None:
    served, _ = dispatcher()

    for path in (BASE, f"{BASE}/billing.refund"):
        _, _, body = request(served, path)
        assert "not permission to invoke it" in body


# --- one capability --------------------------------------------------------


def test_a_capability_page_shows_what_was_published() -> None:
    served, _ = dispatcher()

    status, _, body = request(served, f"{BASE}/billing.refund")

    assert status == 200
    assert "<h1>billing.refund</h1>" in body
    assert f'<a href="{BASE}">Back to the index</a>' in body
    assert "<dt>Risk</dt><dd>high</dd>" in body
    assert "<dt>Idempotency</dt><dd>no</dd>" in body
    assert "<dt>Effects</dt><dd>financial-write</dd>" in body
    assert "<dt>Required scopes</dt><dd>billing:write</dd>" in body
    assert "<li>payment_id (required)" in body
    assert "<li>http: POST /refunds</li>" in body
    assert "<li>mcp: billing.refund</li>" in body
    assert "<li>ledger: Ledger</li>" in body


def test_a_capability_with_no_inputs_says_so_when_inputs_are_published() -> None:
    served, _ = dispatcher()

    _, _, body = request(served, f"{BASE}/billing.health")

    assert "This capability takes no inputs." in body


def test_a_withheld_field_is_named_rather_than_shown_as_a_default() -> None:
    served, _ = dispatcher(route(visibility=DiscoveryVisibility.identity_only(ScopeVisible())))

    _, _, body = request(served, f"{BASE}/billing.refund")

    assert "<dt>Risk</dt>" not in body
    assert "Partial view." in body
    assert "safety" in body


# --- states ----------------------------------------------------------------


def test_a_viewer_who_sees_nothing_gets_a_page_saying_so() -> None:
    served, _ = dispatcher(
        route(
            visibility=DiscoveryVisibility.agent_safe(
                Hiding({"billing.refund", "billing.health"}, ScopeVisible())
            )
        )
    )

    status, _, body = request(served)

    # Nothing visible is a page, not an error.
    assert status == 200
    assert "No capabilities are visible to you." in body
    assert "billing.refund" not in body
    # And it still says that presence is not the same as permission.
    assert "not permission to invoke it" in body


def test_a_viewer_without_a_scope_sees_only_what_declares_none() -> None:
    served, _ = dispatcher(
        route(principals=lambda scope: Principal("reader", scopes={"other:read"}))
    )

    _, _, body = request(served)

    assert "billing.health" in body
    assert "billing.refund" not in body


def test_a_hidden_capability_and_an_absent_one_are_the_same_answer() -> None:
    served, _ = dispatcher(
        route(principals=lambda scope: Principal("reader", scopes={"other:read"}))
    )

    hidden = request(served, f"{BASE}/billing.refund")
    absent = request(served, f"{BASE}/billing.does-not-exist")

    assert hidden[0] == absent[0] == 404
    # The two problems differ only in the target the client itself asked for.
    # Nothing in either says whether the capability exists.
    for document in (json.loads(hidden[2]), json.loads(absent[2])):
        assert document["code"] == "not_found"
        assert document["title"] == "Not Found"
        assert document["detail"] == "no capability is visible at this target"
    assert json.loads(hidden[2]).keys() == json.loads(absent[2]).keys()


def test_an_unidentified_viewer_is_challenged() -> None:
    served, _ = dispatcher(route(principals=lambda scope: None))

    status, headers, body = request(served)

    assert status == 401
    assert headers[b"www-authenticate"] == b"Bearer"
    assert "billing" not in body


def test_a_resolver_that_raises_fails_closed() -> None:
    def explode(scope: dict[str, Any]) -> Principal | None:
        raise RuntimeError("token store unreachable")

    served, _ = dispatcher(route(principals=explode))

    status, _, body = request(served)

    assert status == 500
    assert "token store unreachable" not in body
    assert "billing" not in body


# --- safety ----------------------------------------------------------------


def test_the_page_loads_nothing_and_says_so_in_its_policy() -> None:
    served, _ = dispatcher()

    _, headers, body = request(served)

    assert headers[b"content-security-policy"] == (
        b"default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"referrer-policy"] == b"no-referrer"
    assert headers[b"cache-control"] == b"private, no-store"
    # The policy is only honest because the page genuinely loads nothing.
    assert "<script" not in body
    assert "<style" not in body
    assert "<link" not in body
    assert "<img" not in body
    assert "<form" not in body


def test_the_shell_is_read_only_by_construction() -> None:
    served, _ = dispatcher()

    for path in (BASE, f"{BASE}/billing.refund"):
        _, _, body = request(served, path)
        assert "<button" not in body
        assert "<input" not in body
        assert "onclick" not in body
        assert not re.search(r"\son[a-z]+=", body)


@pytest.mark.parametrize("path", [BASE, f"{BASE}/billing.refund"])
def test_application_controlled_text_cannot_inject_markup(path: str) -> None:
    served, _ = dispatcher(route(snapshot=built(hostile=True)))

    status, _, body = request(served, path)

    assert status == 200
    assert "<script>alert" not in body
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in body


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_another_method_is_refused_with_allow(method: str) -> None:
    served, _ = dispatcher()

    status, headers, _ = request(served, BASE, method)

    assert status == 405
    assert headers[b"allow"] == b"GET, HEAD"


def test_a_head_request_returns_the_headers_without_a_body() -> None:
    served, _ = dispatcher()

    get_status, get_headers, get_body = request(served)
    head_status, head_headers, head_body = request(served, BASE, "HEAD")

    assert head_status == get_status == 200
    assert head_headers == get_headers
    assert head_body == ""
    assert get_body


def test_a_path_outside_the_subtree_is_delegated_unchanged() -> None:
    served, fallback = dispatcher()

    status, _, body = request(served, "/v1/refunds")

    assert status == 299
    assert body == "fallback"
    assert fallback.paths == ["/v1/refunds"]


def test_a_nested_path_inside_the_subtree_is_not_a_capability() -> None:
    served, fallback = dispatcher()

    status, _, _ = request(served, f"{BASE}/billing.refund/extra")

    assert status == 404
    assert fallback.paths == []
