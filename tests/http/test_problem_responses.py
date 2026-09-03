"""RFC 9457 failure projection for the HTTP adapter (E6.5)."""

import asyncio
import json
from typing import Any

import pytest

from agnara.execution import Failure, FailureCode, Success
from agnara_http._problem import (
    _ABOUT_BLANK,
    _INTERNAL_PROBLEM,
    _PROBLEM_MEDIA_TYPE,
    _PROBLEMS,
    _compile_problem_types,
    _ProblemDefinitionError,
    _serialize_failure,
    _serialize_result,
)
from agnara_http._response import _ResponseSerializationError, _send_response

EXPECTED_STATUS = {
    FailureCode.INVALID_INPUT: 400,
    FailureCode.UNAUTHENTICATED: 401,
    FailureCode.FORBIDDEN: 403,
    FailureCode.NOT_FOUND: 404,
    FailureCode.CONFLICT: 409,
    FailureCode.INTERACTION_REQUIRED: 428,
    FailureCode.RATE_LIMITED: 429,
    FailureCode.INTERNAL_FAILURE: 500,
    FailureCode.UNAVAILABLE: 503,
    FailureCode.TIMEOUT: 504,
}


def _document(response: Any) -> dict[str, Any]:
    return json.loads(response.body.decode("utf-8"))


def test_every_failure_code_has_exactly_one_reviewed_status_and_title() -> None:
    assert set(_PROBLEMS) == set(FailureCode)
    assert {code: mapping.status for code, mapping in _PROBLEMS.items()} == EXPECTED_STATUS
    titles = [mapping.title for mapping in _PROBLEMS.values()]
    assert len(set(titles)) == len(titles)
    assert all(title == title.strip() and title for title in titles)


@pytest.mark.parametrize(("code", "status"), sorted(EXPECTED_STATUS.items()))
def test_failure_code_projects_to_its_documented_status(code: FailureCode, status: int) -> None:
    response = _serialize_failure(Failure(code, "rejected"))
    assert response.status == status
    assert _document(response)["status"] == status
    assert _document(response)["code"] == code.value


def test_title_is_occurrence_independent_while_detail_is_not() -> None:
    first = _document(_serialize_failure(Failure(FailureCode.CONFLICT, "version 3 is stale")))
    second = _document(_serialize_failure(Failure(FailureCode.CONFLICT, "row already exists")))

    assert first["title"] == second["title"] == "Conflict"
    assert first["detail"] == "version 3 is stale"
    assert second["detail"] == "row already exists"


def test_problem_document_is_deterministic_compact_utf8_json_with_exact_headers() -> None:
    failure = Failure(
        FailureCode.INVALID_INPUT,
        "unexpected input ñ",
        details={"path": ("user", "age"), "limit": 10, "nullable": None, "ok": False},
    )
    response = _serialize_failure(failure, instance="/v1/users/7")

    assert response.status == 400
    assert response.body == (
        b'{"code":"invalid_input","detail":"unexpected input \xc3\xb1",'
        b'"details":{"limit":10,"nullable":null,"ok":false,"path":["user","age"]},'
        b'"instance":"/v1/users/7","status":400,"title":"Invalid Input","type":"about:blank"}'
    )
    assert response.headers == (
        (b"content-type", b"application/problem+json"),
        (b"content-length", str(len(response.body)).encode("ascii")),
    )
    assert _serialize_failure(failure, instance="/v1/users/7").body == response.body


def test_media_type_is_the_registered_problem_type_without_parameters() -> None:
    assert _PROBLEM_MEDIA_TYPE == b"application/problem+json"
    response = _serialize_failure(Failure(FailureCode.NOT_FOUND, "missing"))
    assert response.headers[0] == (b"content-type", b"application/problem+json")


def test_details_member_is_absent_when_the_failure_carries_none() -> None:
    document = _document(_serialize_failure(Failure(FailureCode.NOT_FOUND, "missing")))
    assert set(document) == {"code", "detail", "status", "title", "type"}


def test_instance_member_is_absent_unless_the_dispatcher_supplies_a_target() -> None:
    assert "instance" not in _document(_serialize_failure(Failure(FailureCode.TIMEOUT, "slow")))


def test_details_never_shadow_reserved_rfc_9457_members() -> None:
    failure = Failure(
        FailureCode.FORBIDDEN,
        "scope missing",
        details={"status": 200, "title": "spoofed", "type": "https://evil.test/"},
    )
    document = _document(_serialize_failure(failure, instance="/v1/orders"))

    assert document["status"] == 403
    assert document["title"] == "Forbidden"
    assert document["type"] == _ABOUT_BLANK
    assert document["details"] == {"status": 200, "title": "spoofed", "type": "https://evil.test/"}


def test_internal_failure_redacts_handler_message_and_details() -> None:
    failure = Failure(
        FailureCode.INTERNAL_FAILURE,
        "psycopg: password authentication failed for the agnara role",
        details={"dsn": "postgres://agnara:s3cret@db.internal/agnara"},
    )
    document = _document(_serialize_failure(failure))

    assert document["status"] == 500
    assert document["detail"] == "The server could not complete the capability invocation."
    assert "details" not in document
    assert "s3cret" not in json.dumps(document)
    assert "psycopg" not in json.dumps(document)


def test_interaction_required_details_project_as_nested_json_arrays() -> None:
    failure = Failure(
        FailureCode.INTERACTION_REQUIRED,
        "confirm the transfer",
        details={
            "kind": "confirmation",
            "capability_id": "payments.transfer",
            "hints": (("amount", "120.00"), ("currency", "EUR")),
        },
    )
    document = _document(_serialize_failure(failure))

    assert document["status"] == 428
    assert document["details"]["hints"] == [["amount", "120.00"], ["currency", "EUR"]]


def test_default_problem_type_is_about_blank_for_every_code() -> None:
    for code in FailureCode:
        assert _document(_serialize_failure(Failure(code, "rejected")))["type"] == _ABOUT_BLANK


def test_compiled_base_uri_produces_stable_per_code_problem_types() -> None:
    types = _compile_problem_types("https://example.test/problems/")

    assert set(types) == set(FailureCode)
    assert types[FailureCode.INVALID_INPUT] == "https://example.test/problems/invalid-input"
    assert types[FailureCode.INTERNAL_FAILURE] == "https://example.test/problems/internal-failure"
    document = _document(
        _serialize_failure(Failure(FailureCode.RATE_LIMITED, "slow down"), problem_types=types)
    )
    assert document["type"] == "https://example.test/problems/rate-limited"


def test_compiled_problem_types_are_read_only() -> None:
    types = _compile_problem_types("https://example.test/problems/")
    mutable: Any = types
    with pytest.raises(TypeError):
        mutable[FailureCode.CONFLICT] = "https://example.test/other"


@pytest.mark.parametrize(
    "base_uri",
    [
        "",
        "problems/",
        "https://example.test/problems",
        "https://example.test/problems/?v=1",
        "https://example.test/problems/#top",
        "https://example.test/pro blems/",
        "https://example.test/problemás/",
        "https://example.test/problems/\n",
    ],
)
def test_rejects_unusable_problem_type_base_uri(base_uri: str) -> None:
    with pytest.raises(_ProblemDefinitionError):
        _compile_problem_types(base_uri)


def test_rejects_non_string_problem_type_base_uri() -> None:
    with pytest.raises(_ProblemDefinitionError, match="non-empty string"):
        _compile_problem_types(7)  # ty: ignore[invalid-argument-type]


def test_rejects_incomplete_problem_type_mapping() -> None:
    with pytest.raises(_ResponseSerializationError, match="no problem type"):
        _serialize_failure(Failure(FailureCode.CONFLICT, "stale"), problem_types={})


@pytest.mark.parametrize(
    "instance",
    ["", "/v1/orders/a b", "/v1/órdenes", "/v1/orders/\x00", "/v1/orders/\x7f"],
)
def test_rejects_instances_that_are_not_uri_references(instance: str) -> None:
    with pytest.raises(_ResponseSerializationError, match="problem instance"):
        _serialize_failure(Failure(FailureCode.NOT_FOUND, "missing"), instance=instance)


def test_accepts_a_percent_encoded_request_target_as_instance() -> None:
    response = _serialize_failure(
        Failure(FailureCode.NOT_FOUND, "missing"), instance="/v1/%C3%B3rdenes/7?full=1"
    )
    assert _document(response)["instance"] == "/v1/%C3%B3rdenes/7?full=1"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_detail_values_before_response_start(value: float) -> None:
    failure = Failure(FailureCode.INVALID_INPUT, "bad number", details={"seen": value})
    with pytest.raises(_ResponseSerializationError, match="non-finite"):
        _serialize_failure(failure)


def test_rejects_a_success_outcome() -> None:
    with pytest.raises(TypeError, match="must be Failure"):
        _serialize_failure(Success("ok"))  # ty: ignore[invalid-argument-type]


def test_last_resort_internal_problem_is_prebuilt_and_stable() -> None:
    assert _INTERNAL_PROBLEM.status == 500
    document = _document(_INTERNAL_PROBLEM)
    assert document == {
        "code": "internal_failure",
        "detail": "The server could not complete the capability invocation.",
        "status": 500,
        "title": "Internal Server Error",
        "type": _ABOUT_BLANK,
    }
    assert (
        _INTERNAL_PROBLEM.body
        == _serialize_failure(Failure(FailureCode.INTERNAL_FAILURE, "anything else")).body
    )


def test_canonical_outcome_entry_point_routes_to_the_matching_boundary() -> None:
    success = _serialize_result(Success({"ok": True}))
    assert success.status == 200
    assert success.headers[0] == (b"content-type", b"application/json; charset=utf-8")

    failure = _serialize_result(Failure(FailureCode.FORBIDDEN, "scope missing"))
    assert failure.status == 403
    assert failure.headers[0] == (b"content-type", b"application/problem+json")

    with pytest.raises(TypeError, match="Success or Failure"):
        _serialize_result("ok")  # ty: ignore[invalid-argument-type]


def test_problem_response_emits_exact_asgi_events_and_supports_head() -> None:
    async def run_test() -> None:
        response = _serialize_failure(Failure(FailureCode.UNAVAILABLE, "database offline"))
        messages: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)

        await _send_response(response, send)
        assert messages == [
            {
                "type": "http.response.start",
                "status": 503,
                "headers": list(response.headers),
            },
            {"type": "http.response.body", "body": response.body, "more_body": False},
        ]

        head: list[dict[str, Any]] = []

        async def send_head(message: dict[str, Any]) -> None:
            head.append(message)

        await _send_response(response, send_head, head=True)
        assert head[0]["headers"] == list(response.headers)
        assert head[1] == {"type": "http.response.body", "body": b"", "more_body": False}

    asyncio.run(run_test())
