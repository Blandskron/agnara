"""Transport-level request failures and their RFC 9457 projection (E6.6a)."""

import asyncio
import json
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition as _CapabilityDefinition
from agnara.capability import CapabilityId as _CapabilityId
from agnara.core.di import DIRegistry as _DIRegistry
from agnara.execution import ExecutionPlan as _ExecutionPlan
from agnara.execution import Failure, FailureCode
from agnara_http._binding import (
    _bind_request,
    _BindingFailure,
    _BindingSource,
    _HTTPBindingPlan,
    _InputBinding,
    _RequestBindingError,
)
from agnara_http._problem import (
    _ABOUT_BLANK,
    _PROBLEM_MEDIA_TYPE,
    _TRANSPORT_PROBLEMS,
    _allow_header,
    _compile_problem_types,
    _serialize_failure,
    _serialize_transport_failure,
    _TransportFailure,
    _with_headers,
)
from agnara_http._response import _ResponseSerializationError, _send_response

EXPECTED_STATUS = {
    _TransportFailure.INVALID_INPUT: 400,
    _TransportFailure.NOT_FOUND: 404,
    _TransportFailure.METHOD_NOT_ALLOWED: 405,
    _TransportFailure.CONTENT_TOO_LARGE: 413,
    _TransportFailure.UNSUPPORTED_MEDIA_TYPE: 415,
}


def _document(response: Any) -> dict[str, Any]:
    return json.loads(response.body.decode("utf-8"))


def test_every_transport_failure_has_exactly_one_reviewed_status_and_title() -> None:
    assert set(_TRANSPORT_PROBLEMS) == set(_TransportFailure)
    assert {
        failure: mapping.status for failure, mapping in _TRANSPORT_PROBLEMS.items()
    } == EXPECTED_STATUS
    titles = [mapping.title for mapping in _TRANSPORT_PROBLEMS.values()]
    assert len(set(titles)) == len(titles)


@pytest.mark.parametrize(("failure", "status"), sorted(EXPECTED_STATUS.items()))
def test_transport_failure_projects_to_its_documented_status(
    failure: _TransportFailure, status: int
) -> None:
    response = _serialize_transport_failure(failure, "rejected before dispatch")
    assert response.status == status
    document = _document(response)
    assert document["status"] == status
    assert document["code"] == failure.value
    assert document["detail"] == "rejected before dispatch"
    assert document["type"] == _ABOUT_BLANK


def test_transport_problems_use_the_same_document_shape_as_capability_failures() -> None:
    transport = _serialize_transport_failure(
        _TransportFailure.NOT_FOUND,
        "no capability is exposed at this target",
        details={"target": "/v1/unknown"},
        instance="/v1/unknown",
    )
    capability = _serialize_failure(
        Failure(FailureCode.NOT_FOUND, "missing", details={"id": "7"}), instance="/v1/orders/7"
    )

    assert set(_document(transport)) == set(_document(capability))
    assert transport.headers[0] == (b"content-type", _PROBLEM_MEDIA_TYPE)
    assert transport.headers[1] == (
        b"content-length",
        str(len(transport.body)).encode("ascii"),
    )


def test_transport_and_capability_codes_coincide_where_the_semantics_do() -> None:
    transport = _document(_serialize_transport_failure(_TransportFailure.NOT_FOUND, "no route"))
    capability = _document(_serialize_failure(Failure(FailureCode.NOT_FOUND, "missing")))
    assert transport["code"] == capability["code"] == "not_found"

    # And a transport-only condition keeps a code of its own.
    only_transport = {failure.value for failure in _TransportFailure} - {
        code.value for code in FailureCode
    }
    assert only_transport == {
        "method_not_allowed",
        "content_too_large",
        "unsupported_media_type",
    }


def test_title_stays_occurrence_independent() -> None:
    first = _document(_serialize_transport_failure(_TransportFailure.INVALID_INPUT, "bad query"))
    second = _document(_serialize_transport_failure(_TransportFailure.INVALID_INPUT, "bad header"))
    assert first["title"] == second["title"] == "Invalid Input"
    assert first["detail"] != second["detail"]


def test_details_and_instance_are_omitted_unless_supplied() -> None:
    document = _document(_serialize_transport_failure(_TransportFailure.NOT_FOUND, "no route"))
    assert set(document) == {"code", "detail", "status", "title", "type"}


def test_the_compiled_namespace_covers_transport_codes() -> None:
    types = _compile_problem_types("https://example.test/problems/")
    document = _document(
        _serialize_transport_failure(
            _TransportFailure.METHOD_NOT_ALLOWED,
            "the target does not accept DELETE",
            headers=_allow_header(("GET",)),
            problem_types=types,
        )
    )
    assert document["type"] == "https://example.test/problems/method-not-allowed"


def test_an_incomplete_problem_type_namespace_is_refused() -> None:
    with pytest.raises(_ResponseSerializationError, match="no problem type"):
        _serialize_transport_failure(_TransportFailure.NOT_FOUND, "no route", problem_types={})


def test_a_405_carries_a_deterministic_allow_header() -> None:
    response = _serialize_transport_failure(
        _TransportFailure.METHOD_NOT_ALLOWED,
        "the target does not accept DELETE",
        headers=_allow_header(("GET", "POST", "PATCH")),
    )
    assert response.status == 405
    assert response.headers[-1] == (b"allow", b"GET, POST, PATCH")
    # The header travels inside the serialized response, so emission cannot
    # drop it.
    assert (b"allow", b"GET, POST, PATCH") in response.headers


def test_an_allow_header_without_methods_is_refused() -> None:
    with pytest.raises(_ResponseSerializationError, match="at least one allowed method"):
        _allow_header(())


@pytest.mark.parametrize("name", [b"content-type", b"Content-Length", b"CONTENT-TYPE"])
def test_added_headers_cannot_shadow_the_representation_headers(name: bytes) -> None:
    response = _serialize_transport_failure(_TransportFailure.NOT_FOUND, "no route")
    with pytest.raises(_ResponseSerializationError, match="owned by the response boundary"):
        _with_headers(response, ((name, b"text/plain"),))


def test_added_headers_must_be_byte_pairs() -> None:
    response = _serialize_transport_failure(_TransportFailure.NOT_FOUND, "no route")
    with pytest.raises(TypeError, match="must be byte pairs"):
        _with_headers(response, (("allow", b"GET"),))  # ty: ignore[invalid-argument-type]


def test_adding_no_headers_returns_the_same_response() -> None:
    response = _serialize_transport_failure(_TransportFailure.NOT_FOUND, "no route")
    assert _with_headers(response, ()) is response


@pytest.mark.parametrize(
    ("failure", "detail"),
    [
        (object(), "must be a _TransportFailure"),
        (FailureCode.NOT_FOUND, "must be a _TransportFailure"),
    ],
)
def test_a_capability_failure_code_is_not_a_transport_failure(failure: object, detail: str) -> None:
    with pytest.raises(TypeError, match=detail):
        _serialize_transport_failure(failure, "no route")  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("detail", ["", None, 7])
def test_a_transport_problem_requires_a_non_empty_detail(detail: object) -> None:
    with pytest.raises(TypeError, match="detail must be a non-empty string"):
        _serialize_transport_failure(_TransportFailure.NOT_FOUND, detail)  # ty: ignore[invalid-argument-type]


def test_a_transport_problem_emits_the_exact_asgi_event_pair() -> None:
    async def run_test() -> None:
        response = _serialize_transport_failure(
            _TransportFailure.UNSUPPORTED_MEDIA_TYPE, "expected application/json"
        )
        messages: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)

        await _send_response(response, send)
        assert messages == [
            {
                "type": "http.response.start",
                "status": 415,
                "headers": list(response.headers),
            },
            {"type": "http.response.body", "body": response.body, "more_body": False},
        ]

    asyncio.run(run_test())


def test_binding_errors_default_to_malformed() -> None:
    error = _RequestBindingError("invalid integer value", location="query.limit")
    assert error.failure is _BindingFailure.MALFORMED
    assert error.location == "query.limit"
    assert error.message == "invalid integer value"
    assert str(error) == "query.limit: invalid integer value"


def json_body_plan(*, max_body_bytes: int = 1_048_576) -> Any:
    def handler(order: dict[str, Any], limit: int = 10) -> None:
        del order, limit

    return _HTTPBindingPlan.compile(
        _ExecutionPlan.compile(
            _CapabilityDefinition(_CapabilityId("tests", "transport"), handler), _DIRegistry()
        ),
        (),
        (
            _InputBinding("order", _BindingSource.BODY),
            _InputBinding("limit", _BindingSource.QUERY),
        ),
        max_body_bytes=max_body_bytes,
    )


def bind(plan: Any, *, headers: Any = (), query: bytes = b"", events: Any = ()) -> None:
    pending = iter(events)

    async def receive() -> dict[str, Any]:
        return next(pending)

    asyncio.run(
        _bind_request(
            plan,
            path_parameters={},
            query_string=query,
            headers=headers,
            receive=receive,
        )
    )


JSON_HEADER = ((b"content-type", b"application/json"),)


def test_a_declined_media_type_is_classified_as_unsupported() -> None:
    with pytest.raises(_RequestBindingError) as raised:
        bind(json_body_plan(), headers=((b"content-type", b"text/plain"),))
    assert raised.value.failure is _BindingFailure.UNSUPPORTED_MEDIA_TYPE
    assert raised.value.location == "header.content-type"


def test_a_missing_content_type_is_classified_as_unsupported() -> None:
    with pytest.raises(_RequestBindingError) as raised:
        bind(json_body_plan())
    assert raised.value.failure is _BindingFailure.UNSUPPORTED_MEDIA_TYPE


def test_an_oversized_body_is_classified_as_content_too_large() -> None:
    with pytest.raises(_RequestBindingError) as raised:
        bind(
            json_body_plan(max_body_bytes=4),
            headers=JSON_HEADER,
            events=({"type": "http.request", "body": b'{"a": 1}', "more_body": False},),
        )
    assert raised.value.failure is _BindingFailure.CONTENT_TOO_LARGE


def test_a_client_disconnect_is_classified_as_disconnected() -> None:
    with pytest.raises(_RequestBindingError) as raised:
        bind(
            json_body_plan(),
            headers=JSON_HEADER,
            events=({"type": "http.disconnect"},),
        )
    assert raised.value.failure is _BindingFailure.DISCONNECTED


@pytest.mark.parametrize(
    ("query", "events"),
    [
        (b"limit=abc", ({"type": "http.request", "body": b"{}", "more_body": False},)),
        (b"limit=%zz", ({"type": "http.request", "body": b"{}", "more_body": False},)),
        (b"", ({"type": "http.request", "body": b"{oops}", "more_body": False},)),
        (b"", ({"type": "agnara.unexpected"},)),
    ],
)
def test_everything_else_is_classified_as_malformed(query: bytes, events: Any) -> None:
    with pytest.raises(_RequestBindingError) as raised:
        bind(json_body_plan(), headers=JSON_HEADER, query=query, events=events)
    assert raised.value.failure is _BindingFailure.MALFORMED


#: The status a dispatcher owes each answerable binding failure. A disconnect
#: is absent on purpose: there is nobody left to answer, so the reason exists
#: for a dispatcher to stop on rather than to select a status.
ANSWERABLE = {
    _BindingFailure.MALFORMED: _TransportFailure.INVALID_INPUT,
    _BindingFailure.UNSUPPORTED_MEDIA_TYPE: _TransportFailure.UNSUPPORTED_MEDIA_TYPE,
    _BindingFailure.CONTENT_TOO_LARGE: _TransportFailure.CONTENT_TOO_LARGE,
}


def test_every_binding_failure_is_either_answerable_or_a_disconnect() -> None:
    assert set(ANSWERABLE) | {_BindingFailure.DISCONNECTED} == set(_BindingFailure)


@pytest.mark.parametrize(("reason", "transport"), sorted(ANSWERABLE.items()))
def test_each_answerable_binding_failure_has_a_reviewed_status(
    reason: _BindingFailure, transport: _TransportFailure
) -> None:
    del reason
    assert transport in _TRANSPORT_PROBLEMS
    assert _TRANSPORT_PROBLEMS[transport].status in {400, 413, 415}
