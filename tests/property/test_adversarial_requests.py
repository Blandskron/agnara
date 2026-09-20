"""Bounded fuzzing of the whole request path, from ASGI scope to response.

`tests/security/test_http_protocol_robustness.py` proves the contract for the
malformed requests someone thought of. This lane generates them instead, and
asserts only the invariant that must hold for every input:

    one reviewed response, or a deliberate silence when the client is gone.

An exception escaping into the ASGI server breaks that contract, because the
server -- not Agnara -- then decides what the client and the operator's log
receive, bypassing the reviewed problem mapping and its redaction. F-1 was
found exactly here.

The bounds are deliberate and small. Bodies, header counts and path lengths
are capped well below the adapter's own limits, because the point is shape
coverage rather than load: a size limit already has its own focused test, and
an unbounded strategy would turn a shared CI lane into a cost centre.
"""

from __future__ import annotations

import json
from typing import Any

from hypothesis import example, given
from hypothesis import strategies as st

from agnara_http._binding import _BindingSource, _InputBinding
from agnara_http._dispatch import _HTTPExposure
from tests.http.test_dispatch import dispatcher, plan, request

TERMINAL = {"http.response.start", "http.response.body"}


def echo(payload: Any) -> Any:
    return payload


def scalar(payload: str) -> str:
    return payload


def served() -> Any:
    """One dispatcher exposing a body route, a scalar route and a path parameter."""
    return dispatcher(
        _HTTPExposure(
            "POST",
            "/body",
            plan(echo, "body"),
            bindings=(_InputBinding("payload", _BindingSource.BODY),),
        ),
        _HTTPExposure(
            "GET",
            "/query",
            plan(scalar, "query"),
            bindings=(_InputBinding("payload", _BindingSource.QUERY),),
        ),
        _HTTPExposure(
            "GET",
            "/item/{payload}",
            plan(scalar, "item"),
            bindings=(_InputBinding("payload", _BindingSource.PATH),),
        ),
    )


#: Header names and values are bytes on the wire and attacker controlled.
header_bytes = st.binary(min_size=0, max_size=24)
headers = st.lists(st.tuples(header_bytes, header_bytes), max_size=6).map(tuple)

#: Bounded: the 1 MiB body ceiling has its own focused test.
bodies = st.one_of(
    st.binary(max_size=256),
    st.text(max_size=128).map(str.encode),
    st.builds(
        lambda value: json.dumps(value).encode(),
        st.recursive(
            st.one_of(st.none(), st.booleans(), st.integers(-1000, 1000), st.text(max_size=8)),
            lambda children: st.one_of(
                st.lists(children, max_size=3),
                st.dictionaries(st.text(max_size=4), children, max_size=3),
            ),
            max_leaves=8,
        ),
    ),
)

paths = st.one_of(
    st.just("/body"),
    st.just("/query"),
    st.text(max_size=32),
    st.text(alphabet="/abc%.{}[]\\ ", max_size=16),
)

methods = st.one_of(
    st.sampled_from(["GET", "POST", "HEAD", "OPTIONS", "PUT", "DELETE"]),
    st.text(max_size=8),
)


def assert_one_reviewed_answer(events: list[dict[str, Any]]) -> None:
    """Either a complete reviewed response, or nothing at all."""
    if not events:
        return
    assert events[0]["type"] == "http.response.start", events[0]
    status = events[0]["status"]
    assert isinstance(status, int) and 100 <= status <= 599, status
    assert all(event["type"] in TERMINAL for event in events), events
    # Exactly one start, and the body events follow it.
    assert [event["type"] for event in events].count("http.response.start") == 1


@given(method=methods, path=paths, body=bodies, extra=headers)
# F-1: a method outside the RFC 9110 token grammar raised out of the
# dispatcher instead of answering, echoing the caller's own bytes.
@example(method="BAD METHOD", path="/body", body=b"{}", extra=())
@example(method="GET\x00", path="/body", body=b"{}", extra=())
@example(method="", path="/body", body=b"{}", extra=())
# Targets an ASGI server may pass through unchanged.
@example(method="OPTIONS", path="*", body=b"", extra=())
@example(method="GET", path="http://elsewhere.example/body", body=b"", extra=())
# Bodies the JSON binder must refuse rather than crash on.
@example(method="POST", path="/body", body=b"", extra=())
@example(method="POST", path="/body", body=b"\xff\xfe\x00", extra=())
@example(method="POST", path="/body", body=b"[" * 64, extra=())
@example(method="POST", path="/body", body=b'{"payload":', extra=())
def test_any_request_produces_one_reviewed_answer_or_silence(
    method: str, path: str, body: bytes, extra: tuple[tuple[bytes, bytes], ...]
) -> None:
    events = request(
        served(),
        method,
        path,
        headers=((b"content-type", b"application/json"), *extra),
        body=body,
    )

    assert_one_reviewed_answer(events)


@given(query=st.binary(max_size=64), method=st.sampled_from(["GET", "HEAD"]))
@example(query=b"payload=%", method="GET")
@example(query=b"payload=%zz", method="GET")
@example(query=b"\xff\xfe", method="GET")
@example(query=b"payload=a&payload=b", method="GET")
@example(query=b"payload", method="GET")
def test_any_query_string_produces_one_reviewed_answer(query: bytes, method: str) -> None:
    events = request(served(), method, "/query", query=query)

    assert_one_reviewed_answer(events)


@given(segment=st.text(max_size=24))
@example(segment="%2e%2e")
@example(segment="..")
@example(segment="\x00")
@example(segment="a/b")
def test_any_path_parameter_produces_one_reviewed_answer(segment: str) -> None:
    events = request(served(), "GET", f"/item/{segment}")

    assert_one_reviewed_answer(events)


@given(extra=headers)
@example(extra=((b"content-type", b"application/json; charset=\xff"),))
@example(extra=((b"content-type", b""),))
@example(extra=((b"content-length", b"not-a-number"),))
@example(extra=((b"", b""),))
def test_any_header_set_produces_one_reviewed_answer(
    extra: tuple[tuple[bytes, bytes], ...],
) -> None:
    events = request(served(), "POST", "/body", headers=extra, body=b'{"payload": 1}')

    assert_one_reviewed_answer(events)


@given(method=methods, path=paths)
def test_a_disconnected_client_is_answered_with_silence_or_one_response(
    method: str, path: str
) -> None:
    """Cancellation is control flow, not a failure to report."""
    events = request(served(), method, path, disconnect=True)

    assert_one_reviewed_answer(events)


@given(body=bodies, extra=headers)
def test_a_refusal_never_echoes_the_body_it_refused(
    body: bytes, extra: tuple[tuple[bytes, bytes], ...]
) -> None:
    """A problem document must not reflect attacker bytes back to the caller.

    Reflection is both a disclosure channel and, for a document rendered into
    a browser surface, an injection one.
    """
    marker = b"zqxjmarker"
    events = request(
        served(),
        "POST",
        "/body",
        headers=((b"content-type", b"application/json"), *extra),
        body=marker + body,
    )

    rendered = b"".join(event.get("body", b"") for event in events)
    status = events[0]["status"] if events else 0
    if status >= 400:
        assert marker not in rendered
