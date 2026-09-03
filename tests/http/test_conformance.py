"""Executable HTTP conformance suite for the whole adapter (E6.8).

Every other module in `tests/http` checks one module's own rules. This checks
the rules that must hold *across* the adapter, on every response path, through
the entry point a server actually calls.

The point is the shared checker. Each exchange below runs through
`conformance()`, so a response path cannot be exercised without being
validated, and a path added later inherits every rule at once.

What is checked
---------------
- ASGI 3.0 / HTTP sub-specification 2.5: the response event pair, its shapes,
  and that nothing follows the terminal body event.
- RFC 9110: `content-length` agreeing with the representation, `HEAD`
  transmitting no body, `204` carrying no representation metadata, `405`
  carrying `Allow`.
- RFC 9457: every error body being a parseable problem document whose `status`
  member agrees with the response status.

What is not checked, because the adapter does not implement it
--------------------------------------------------------------
WebSockets, streaming and multi-chunk bodies, trailers, HTTP/2-specific
behavior, content negotiation, conditional requests, ranges, caching,
authentication challenges and rate-limit headers. This suite is not a claim of
general HTTP conformance; it is a claim about the paths the adapter has.

OpenAPI structure belongs to E6.11, deliberately not here: a failure should
name one specification.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.core.di.resolver import DIContainer
from agnara.execution import ExecutionPlan, Failure, FailureCode
from agnara_http._asgi import _ASGIBoundary
from agnara_http._binding import _BindingSource, _InputBinding
from agnara_http._dispatch import _compile_exposures, _HTTPDispatcher, _HTTPExposure
from agnara_http._lifespan import _LifespanDispatcher

PROBLEM_MEDIA_TYPE = b"application/problem+json"
JSON_MEDIA_TYPE = b"application/json; charset=utf-8"
JSON_REQUEST = ((b"content-type", b"application/json"),)

#: Statuses whose representation metadata RFC 9110 forbids.
BODYLESS = frozenset({204, 205, 304})


class Exchange:
    """One completed request, with the checker already applied."""

    __slots__ = ("body", "events", "head", "headers", "method", "path", "status")

    def __init__(self, method: str, path: str, events: list[dict[str, Any]]) -> None:
        self.method = method
        self.path = path
        self.events = events
        self.head = method == "HEAD"
        self.status = events[0]["status"] if events else None
        self.headers = dict(events[0]["headers"]) if events else {}
        self.body = events[1]["body"] if len(events) > 1 else b""

    def document(self) -> dict[str, Any]:
        return json.loads(self.body.decode("utf-8"))


# --- the checker -----------------------------------------------------------


def conformance(exchange: Exchange, *, representation_length: int | None = None) -> Exchange:
    """Assert every cross-module invariant for one exchange.

    ``representation_length`` is the byte length the equivalent ``GET`` would
    have produced. It is required for ``HEAD``, where the body is empty but
    ``content-length`` must still describe the representation.
    """
    _check_asgi_events(exchange)
    _check_headers(exchange)
    _check_content_length(exchange, representation_length)
    _check_status_semantics(exchange)
    return exchange


def _check_asgi_events(exchange: Exchange) -> None:
    events = exchange.events
    assert len(events) == 2, f"expected exactly two ASGI events, got {len(events)}"

    start, body = events
    assert start["type"] == "http.response.start"
    assert isinstance(start["status"], int) and not isinstance(start["status"], bool)
    assert 100 <= start["status"] <= 599, f"status out of range: {start['status']}"

    assert body["type"] == "http.response.body"
    assert isinstance(body["body"], bytes)
    # A terminal event either says so or omits the flag; it must never claim
    # more, because nothing here sends a second body event.
    assert body.get("more_body", False) is False


def _check_headers(exchange: Exchange) -> None:
    raw = exchange.events[0]["headers"]
    assert isinstance(raw, list), f"headers must be a list, got {type(raw).__name__}"
    for pair in raw:
        assert isinstance(pair, tuple | list) and len(pair) == 2, f"malformed header {pair!r}"
        name, value = pair
        assert isinstance(name, bytes) and isinstance(value, bytes), f"header not bytes: {pair!r}"
        assert name == name.lower(), f"header name is not lowercase: {name!r}"

    names = [name for name, _ in raw]
    for single in (b"content-type", b"content-length"):
        assert names.count(single) <= 1, f"{single!r} appears more than once"


def _check_content_length(exchange: Exchange, representation_length: int | None) -> None:
    declared = exchange.headers.get(b"content-length")
    if declared is None:
        return
    length = int(declared)
    if exchange.head:
        assert representation_length is not None, (
            "a HEAD exchange must be checked against its GET representation length"
        )
        assert length == representation_length, (
            f"HEAD content-length {length} does not describe the GET representation "
            f"({representation_length})"
        )
        assert exchange.body == b"", "HEAD transmitted body bytes"
        return
    assert length == len(exchange.body), (
        f"content-length {length} does not match the {len(exchange.body)} bytes sent"
    )


def _check_status_semantics(exchange: Exchange) -> None:
    status = exchange.status
    assert status is not None
    media_type = exchange.headers.get(b"content-type")

    if status in BODYLESS:
        assert media_type is None, f"{status} carries a content-type"
        assert b"content-length" not in exchange.headers, f"{status} carries a content-length"
        assert exchange.body == b"", f"{status} carries a body"
        return

    if status >= 400:
        assert media_type == PROBLEM_MEDIA_TYPE, (
            f"{status} is not application/problem+json, got {media_type!r}"
        )
        if not exchange.head:
            document = exchange.document()
            assert document["status"] == status, (
                f"problem status member {document['status']} disagrees with the response {status}"
            )
            for member in ("type", "title", "status", "code"):
                assert member in document, f"problem is missing {member!r}"
        if status == 405:
            assert b"allow" in exchange.headers, "405 does not carry Allow"
        return

    if 200 <= status < 300:
        assert media_type == JSON_MEDIA_TYPE, (
            f"{status} is not the JSON media type, got {media_type!r}"
        )
        if not exchange.head:
            exchange.document()


# --- the application under test --------------------------------------------


def plan(handler: Callable[..., Any], name: str) -> ExecutionPlan:
    return ExecutionPlan.compile(
        CapabilityDefinition(CapabilityId("conformance", name), handler), DIRegistry()
    )


def show(order_id: int, verbose: bool = False) -> dict[str, Any]:
    return {"order_id": order_id, "verbose": verbose}


def create(order: dict[str, Any]) -> dict[str, Any]:
    return {"created": order}


def archive() -> None:
    return None


def conflicted() -> Failure:
    return Failure(FailureCode.CONFLICT, "version 3 is stale", details={"version": 3})


def exploding() -> None:
    raise RuntimeError("postgres://agnara:s3cret@db.internal refused the connection")


def unserializable() -> object:
    return object()


def application() -> _ASGIBoundary:
    """The composition a server would be handed."""
    routes = _compile_exposures(
        [
            _HTTPExposure(
                "GET",
                "/v1/orders/{order_id}",
                plan(show, "show"),
                (
                    _InputBinding("order_id", _BindingSource.PATH),
                    _InputBinding("verbose", _BindingSource.QUERY),
                ),
            ),
            _HTTPExposure(
                "POST",
                "/v1/orders",
                plan(create, "create"),
                (_InputBinding("order", _BindingSource.BODY),),
                max_body_bytes=32,
            ),
            _HTTPExposure("DELETE", "/v1/orders", plan(archive, "archive")),
            _HTTPExposure("GET", "/v1/empty", plan(archive, "empty")),
            _HTTPExposure("GET", "/v1/conflict", plan(conflicted, "conflict")),
            _HTTPExposure("GET", "/v1/boom", plan(exploding, "boom")),
            _HTTPExposure("GET", "/v1/opaque", plan(unserializable, "opaque")),
        ]
    )
    return _ASGIBoundary(_HTTPDispatcher(routes, DIContainer(DIRegistry())))


def exchange(
    method: str,
    path: str,
    *,
    query: bytes = b"",
    headers: tuple[tuple[bytes, bytes], ...] = (),
    body: bytes = b"",
    disconnect: bool = False,
) -> Exchange:
    """Drive one request through the ASGI entry point a server would call."""
    events: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = (
        [{"type": "http.disconnect"}]
        if disconnect
        else [{"type": "http.request", "body": body, "more_body": False}]
    )

    async def receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    asyncio.run(
        application()(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.5"},
                "http_version": "1.1",
                "scheme": "http",
                "method": method,
                "path": path,
                "raw_path": path.encode("utf-8"),
                "query_string": query,
                "root_path": "",
                "headers": list(headers),
            },
            receive,
            send,
        )
    )
    return Exchange(method, path, events)


# --- the matrix ------------------------------------------------------------

#: Every request the suite performs, and the status it must produce. Adding a
#: row is how a new response path joins the conformance checks.
MATRIX: tuple[tuple[str, dict[str, Any], int], ...] = (
    ("success", {"method": "GET", "path": "/v1/orders/7"}, 200),
    (
        "success with query",
        {"method": "GET", "path": "/v1/orders/7", "query": b"verbose=true"},
        200,
    ),
    (
        "success with body",
        {
            "method": "POST",
            "path": "/v1/orders",
            "headers": JSON_REQUEST,
            "body": b'{"sku":"A-1"}',
        },
        200,
    ),
    ("no content", {"method": "DELETE", "path": "/v1/orders"}, 204),
    ("unmatched path", {"method": "GET", "path": "/v1/absent"}, 404),
    ("unmatched method", {"method": "PATCH", "path": "/v1/orders"}, 405),
    (
        "malformed query value",
        {"method": "GET", "path": "/v1/orders/7", "query": b"verbose=maybe"},
        400,
    ),
    (
        "oversized body",
        {
            "method": "POST",
            "path": "/v1/orders",
            "headers": JSON_REQUEST,
            "body": b'{"sku":"A-1","note":"far too long to fit the limit"}',
        },
        413,
    ),
    (
        "declined media type",
        {
            "method": "POST",
            "path": "/v1/orders",
            "headers": ((b"content-type", b"text/plain"),),
            "body": b"{}",
        },
        415,
    ),
    ("capability failure", {"method": "GET", "path": "/v1/conflict"}, 409),
    ("unexpected exception", {"method": "GET", "path": "/v1/boom"}, 500),
    ("unserializable result", {"method": "GET", "path": "/v1/opaque"}, 500),
)


@pytest.mark.parametrize(
    ("label", "request_kwargs", "status"), MATRIX, ids=[row[0] for row in MATRIX]
)
def test_every_response_path_is_conformant(
    label: str, request_kwargs: dict[str, Any], status: int
) -> None:
    del label
    result = conformance(exchange(**request_kwargs))
    assert result.status == status


def test_the_matrix_covers_every_status_family_the_adapter_produces() -> None:
    # A row that stops producing its status would otherwise pass silently as
    # some other conformant response.
    produced = {status for _, _, status in MATRIX}
    assert produced == {200, 204, 400, 404, 405, 409, 413, 415, 500}


def test_the_checker_rejects_a_non_conformant_exchange() -> None:
    # The suite is only worth its runtime if the checker can fail.
    broken = Exchange(
        "GET",
        "/v1/orders/7",
        [
            {"type": "http.response.start", "status": 200, "headers": [(b"Content-Type", b"x")]},
            {"type": "http.response.body", "body": b"{}", "more_body": False},
        ],
    )
    with pytest.raises(AssertionError, match="not lowercase"):
        conformance(broken)

    truncated = Exchange(
        "GET", "/x", [{"type": "http.response.start", "status": 200, "headers": []}]
    )
    with pytest.raises(AssertionError, match="exactly two ASGI events"):
        conformance(truncated)

    mismatched = Exchange(
        "GET",
        "/x",
        [
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", PROBLEM_MEDIA_TYPE), (b"content-length", b"99")],
            },
            {"type": "http.response.body", "body": b"{}", "more_body": False},
        ],
    )
    with pytest.raises(AssertionError, match="does not match"):
        conformance(mismatched)


# --- HEAD ------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/v1/orders/7", "/v1/absent", "/v1/conflict", "/v1/empty"])
def test_head_matches_its_get_representation_without_sending_it(path: str) -> None:
    get = conformance(exchange("GET", path))
    head = conformance(exchange("HEAD", path), representation_length=len(get.body))

    assert head.status == get.status
    assert head.events[0]["headers"] == get.events[0]["headers"]
    assert head.body == b""


def test_head_on_a_204_stays_bodyless_and_bare() -> None:
    get = conformance(exchange("GET", "/v1/empty"))
    assert get.status == 204

    head = conformance(exchange("HEAD", "/v1/empty"), representation_length=0)
    assert head.status == 204
    assert head.events[0]["headers"] == []


def test_head_without_a_get_at_the_target_is_a_405() -> None:
    # HEAD falls back to GET, not to any method: /v1/orders answers POST and
    # DELETE, so HEAD is refused rather than silently mapped onto one of them.
    equivalent = conformance(exchange("GET", "/v1/orders"))
    result = conformance(exchange("HEAD", "/v1/orders"), representation_length=len(equivalent.body))
    assert equivalent.status == result.status == 405
    assert set(result.headers[b"allow"].decode("ascii").split(", ")) == {"POST", "DELETE"}


# --- rules that span modules ----------------------------------------------


def test_no_response_leaks_handler_exception_text() -> None:
    result = conformance(exchange("GET", "/v1/boom"))
    serialized = result.body.decode("utf-8")

    assert "s3cret" not in serialized
    assert "postgres" not in serialized
    assert "db.internal" not in serialized
    assert result.document()["code"] == "internal_failure"


def test_allow_lists_the_methods_the_target_answers() -> None:
    result = conformance(exchange("PATCH", "/v1/orders"))
    allowed = result.headers[b"allow"].decode("ascii").split(", ")

    assert set(allowed) == {"POST", "DELETE"}
    # HEAD is absent because no GET exposure exists at this target.
    assert "HEAD" not in allowed


def test_allow_advertises_the_head_implied_by_get() -> None:
    result = conformance(exchange("PATCH", "/v1/orders/7"))
    assert result.headers[b"allow"] == b"GET, HEAD"


def test_a_client_disconnect_emits_no_events() -> None:
    result = exchange("POST", "/v1/orders", headers=JSON_REQUEST, disconnect=True)
    assert result.events == []


def test_every_problem_shares_one_document_shape() -> None:
    problems = [
        conformance(exchange(**kwargs)).document() for _, kwargs, status in MATRIX if status >= 400
    ]
    assert len(problems) == len([row for row in MATRIX if row[2] >= 400]) == 8
    for document in problems:
        assert {"type", "title", "status", "code"} <= set(document)
        assert set(document) <= {"type", "title", "status", "detail", "instance", "code", "details"}


def test_a_problem_instance_never_carries_the_query_string() -> None:
    result = conformance(exchange("GET", "/v1/absent", query=b"token=s3cret"))
    document = result.document()

    assert document["instance"] == "/v1/absent"
    assert "s3cret" not in json.dumps(document)


# --- lifespan --------------------------------------------------------------


def lifespan_exchange(*, fail: bool) -> list[dict[str, Any]]:
    @asynccontextmanager
    async def lifecycle() -> AsyncIterator[None]:
        if fail:
            raise RuntimeError("dependency unavailable")
        yield None

    async def http_dispatch(scope: Any, receive: Any, send: Any) -> None:  # pragma: no cover
        del scope, receive, send

    boundary = _ASGIBoundary(http_dispatch, _LifespanDispatcher(lifecycle))
    pending = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    events: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    asyncio.run(boundary({"type": "lifespan"}, receive, send))
    return events


def test_a_healthy_lifespan_completes_both_phases_in_order() -> None:
    assert lifespan_exchange(fail=False) == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]


def test_a_failed_startup_reports_once_and_never_completes() -> None:
    events = lifespan_exchange(fail=True)

    assert len(events) == 1
    assert events[0]["type"] == "lifespan.startup.failed"
    assert isinstance(events[0]["message"], str)
    assert "dependency unavailable" in events[0]["message"]
