"""A4-10: adversarial HTTP/ASGI protocol events against the a4 request path.

Every case here is an attacker-controlled request that reaches the adapter
before any capability runs. The contract under test is the one the dispatcher
states: one reviewed response, or nothing at all when the client is gone. An
exception escaping into the ASGI server breaks that contract, because the
server -- not Agnara -- then decides what the client and the operator's log
receive.

The threat model these cases come from is ``docs/THREAT_MODEL.md``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from agnara_http._binding import (
    _MAX_EMPTY_BODY_EVENTS,
    _MAX_JSON_NESTING,
    _BindingSource,
    _InputBinding,
)
from agnara_http._dispatch import _HTTPExposure
from tests.http.test_dispatch import dispatcher, plan, request

JSON = ((b"content-type", b"application/json"),)


def echo(payload: Any) -> Any:
    return payload


def text_echo(payload: str) -> str:
    """A scalar-bound capability, which every non-body source requires."""
    return payload


def body_route() -> _HTTPExposure:
    return _HTTPExposure(
        "POST",
        "/p",
        plan(echo),
        bindings=(_InputBinding("payload", _BindingSource.BODY),),
    )


def drive(
    served: Any,
    events: list[dict[str, Any]] | None = None,
    *,
    receive: Any = None,
    headers: tuple[tuple[bytes, bytes], ...] = JSON,
    method: str = "POST",
    path: str = "/p",
) -> list[dict[str, Any]]:
    """Drive one request over an arbitrary ASGI event stream."""
    sent: list[dict[str, Any]] = []
    pending = list(events or ())

    async def default_receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def bounded() -> None:
        async with asyncio.timeout(10):
            await served(
                {
                    "type": "http",
                    "method": method,
                    "path": path,
                    "query_string": b"",
                    "root_path": "",
                    "headers": list(headers),
                },
                receive or default_receive,
                send,
            )

    asyncio.run(bounded())
    return sent


def problem(sent: list[dict[str, Any]]) -> dict[str, Any]:
    assert sent[0]["type"] == "http.response.start"
    document: dict[str, Any] = json.loads(sent[1]["body"])
    return document


def test_a_deeply_nested_json_body_is_a_problem_not_an_escaped_exception() -> None:
    """A body the JSON decoder cannot walk is refused like any malformed one.

    80 KB is far inside the default 1 MiB limit, so the size bound never sees
    this request. Without an explicit guard the decoder exhausts the C stack
    and the RecursionError leaves the dispatcher with nothing sent.
    """
    depth = 40_000
    nested = (b"[" * depth) + (b"]" * depth)
    assert len(nested) < 1_048_576

    sent = drive(
        dispatcher(body_route()),
        [{"type": "http.request", "body": nested, "more_body": False}],
    )

    assert sent[0]["status"] == 400
    document = problem(sent)
    assert document["code"] == "invalid_input"
    assert document["details"] == {"location": "body"}
    # The reason is named without echoing any part of the body back.
    assert "nested too deeply" in document["detail"]


def test_json_at_the_nesting_limit_is_still_accepted() -> None:
    """The defensive ceiling has an exact, platform-independent boundary."""
    nested = (b"[" * _MAX_JSON_NESTING) + b"0" + (b"]" * _MAX_JSON_NESTING)

    sent = drive(
        dispatcher(body_route()),
        [{"type": "http.request", "body": nested, "more_body": False}],
    )

    assert sent[0]["status"] == 200


def test_json_nesting_ignores_structural_characters_inside_strings() -> None:
    """An attacker cannot trigger the ceiling with inert string content."""
    value = '[\\"{' * (_MAX_JSON_NESTING + 1)
    body = json.dumps(value).encode()

    sent = drive(
        dispatcher(body_route()),
        [{"type": "http.request", "body": body, "more_body": False}],
    )

    assert sent[0]["status"] == 200
    assert json.loads(sent[1]["body"]) == value


def test_a_result_too_deep_to_serialize_is_a_redacted_500() -> None:
    """A handler's deeply nested output ends at the redacted last resort."""

    def deeply_nested_result() -> Any:
        value: Any = 0
        for _ in range(2_000):
            value = [value]
        return value

    route = _HTTPExposure("GET", "/deep", plan(deeply_nested_result))

    sent = drive(
        dispatcher(route),
        [{"type": "http.request", "body": b"", "more_body": False}],
        headers=(),
        method="GET",
        path="/deep",
    )

    assert sent[0]["status"] == 500
    document = problem(sent)
    assert document["code"] == "internal_failure"
    assert document["detail"] == "The server could not complete the capability invocation."


def test_an_endless_stream_of_empty_body_chunks_terminates() -> None:
    """A chunk carrying no bytes must not buy unlimited time.

    ``max_body_bytes`` counts bytes, and an empty chunk moves it no closer to
    its limit. Left unbounded, a client holding the request open with them
    occupies a worker for as long as it likes.
    """
    calls = 0

    async def receive() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"type": "http.request", "body": b"", "more_body": True}

    sent = drive(dispatcher(body_route()), receive=receive)

    assert sent[0]["status"] == 400
    assert problem(sent)["code"] == "invalid_input"
    assert calls == _MAX_EMPTY_BODY_EVENTS + 1


def test_a_chunked_body_with_a_few_empty_chunks_still_binds() -> None:
    """The bound refuses abuse, not the ordinary shape of a streamed body."""
    events: list[dict[str, Any]] = [
        {"type": "http.request", "body": b"", "more_body": True},
        {"type": "http.request", "body": b'{"a"', "more_body": True},
        {"type": "http.request", "body": b"", "more_body": True},
        {"type": "http.request", "body": b":1}", "more_body": False},
    ]

    sent = drive(dispatcher(body_route()), events)

    assert sent[0]["status"] == 200
    assert json.loads(sent[1]["body"]) == {"a": 1}


def test_a_disconnect_after_a_partial_body_answers_nobody() -> None:
    """A client that vanishes mid-body gets no response and no exception."""
    events: list[dict[str, Any]] = [
        {"type": "http.request", "body": b'{"a"', "more_body": True},
        {"type": "http.disconnect"},
    ]

    assert drive(dispatcher(body_route()), events) == []


def test_a_bound_header_value_cannot_reach_a_response_header() -> None:
    """Header values are input to a capability, never material for a response.

    A value carrying CRLF is the classic response-splitting attempt. It binds
    as opaque text and appears in no emitted header.
    """
    route = _HTTPExposure(
        "GET",
        "/h",
        plan(text_echo),
        bindings=(_InputBinding("payload", _BindingSource.HEADER, "x-trace"),),
    )

    sent = drive(
        dispatcher(route),
        [{"type": "http.request", "body": b"", "more_body": False}],
        headers=((b"x-trace", b"ok\r\nX-Injected: 1"),),
        method="GET",
        path="/h",
    )

    assert sent[0]["status"] == 200
    assert {name for name, _ in sent[0]["headers"]} == {b"content-type", b"content-length"}
    assert json.loads(sent[1]["body"]) == "ok\r\nX-Injected: 1"


def test_a_traversal_sequence_in_a_path_parameter_is_only_data() -> None:
    """Nothing resolves a path parameter against a filesystem or another route."""
    route = _HTTPExposure(
        "GET",
        "/files/{name}",
        plan(text_echo),
        bindings=(_InputBinding("payload", _BindingSource.PATH, "name"),),
    )

    sent = drive(
        dispatcher(route),
        [{"type": "http.request", "body": b"", "more_body": False}],
        headers=(),
        method="GET",
        path="/files/..%2F..%2Fetc%2Fpasswd",
    )

    assert sent[0]["status"] == 200
    assert json.loads(sent[1]["body"]) == "..%2F..%2Fetc%2Fpasswd"


def test_a_json_content_type_with_parameters_is_still_json() -> None:
    """Content-type confusion is settled on the media type alone."""
    sent = drive(
        dispatcher(body_route()),
        [{"type": "http.request", "body": b'{"a":1}', "more_body": False}],
        headers=((b"content-type", b"APPLICATION/JSON; charset=utf-8"),),
    )

    assert sent[0]["status"] == 200


def test_a_form_encoded_body_declared_as_json_is_refused() -> None:
    """Claiming JSON does not make a form body one."""
    sent = drive(
        dispatcher(body_route()),
        [{"type": "http.request", "body": b"a=1&b=2", "more_body": False}],
    )

    assert sent[0]["status"] == 400
    assert problem(sent)["code"] == "invalid_input"


def test_the_request_target_never_carries_a_query_into_a_problem() -> None:
    """A secret passed in a query must not be copied into a problem body."""
    sent = request(
        dispatcher(body_route()),
        "GET",
        "/missing",
        query=b"token=super-secret",
    )

    document = json.loads(sent[1]["body"])
    assert document["status"] == 404
    assert document["instance"] == "/missing"
    assert "super-secret" not in json.dumps(document)


def test_a_request_target_that_is_not_origin_form_is_an_ordinary_404() -> None:
    """``OPTIONS *`` and absolute-form targets reach the adapter as paths that
    do not start with ``/``. They are targets nothing is exposed at, not route
    definition mistakes, and must not escape as an exception the server turns
    into a bare 500."""
    for method, path in (("OPTIONS", "*"), ("GET", "http://example.com/p")):
        sent = drive(dispatcher(body_route()), method=method, path=path, headers=())
        assert sent[0]["status"] == 404
        assert problem(sent)["code"] == "not_found"


def test_a_json_number_that_overflows_to_infinity_is_refused() -> None:
    """``1e400`` is valid JSON text but not a finite value; the query path
    already refuses it and the body path must agree."""
    for body in (b"1e400", b'{"n": -1e999}', b"[1e400]"):
        sent = drive(
            dispatcher(body_route()),
            [{"type": "http.request", "body": body, "more_body": False}],
        )
        assert sent[0]["status"] == 400
        assert problem(sent)["details"] == {"location": "body"}


def test_a_lone_surrogate_escape_is_a_client_error_not_a_server_error() -> None:
    sent = drive(
        dispatcher(body_route()),
        [{"type": "http.request", "body": b'"\\ud800"', "more_body": False}],
    )
    assert sent[0]["status"] == 400
    assert problem(sent)["details"] == {"location": "body"}


def test_a_surrogate_pair_escape_is_still_valid_text() -> None:
    sent = drive(
        dispatcher(body_route()),
        [{"type": "http.request", "body": b'"\\ud83d\\ude00"', "more_body": False}],
    )
    assert sent[0]["status"] == 200
    assert json.loads(sent[1]["body"]) == "\U0001f600"


def test_a_declared_oversized_body_is_refused_before_it_is_read() -> None:
    reads = 0

    async def receive() -> dict[str, Any]:
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": b"x" * 512, "more_body": True}

    sent = drive(
        dispatcher(body_route()),
        receive=receive,
        headers=(*JSON, (b"content-length", b"2000000")),
    )
    assert sent[0]["status"] == 413
    assert reads == 0


def test_json_bodies_with_brackets_only_inside_strings_are_accepted_quickly() -> None:
    """The delimiter count exceeds the limit, so the exact walk runs and must
    still ignore structural characters inside strings."""
    body = json.dumps({"text": "[" * (_MAX_JSON_NESTING + 5)}).encode()
    sent = drive(
        dispatcher(body_route()),
        [{"type": "http.request", "body": body, "more_body": False}],
    )
    assert sent[0]["status"] == 200
