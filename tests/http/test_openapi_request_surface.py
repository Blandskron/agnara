"""The new request sources, as OpenAPI 3.2 says them.

A document that promises an operation the adapter cannot serve is worse than
no document, so each of these asserts the projection against what
`test_request_surface.py` proves the adapter actually accepts.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara_http._binding import _BindingSource, _InputBinding
from agnara_http._dispatch import _compile_exposures, _HTTPExposure, _OpenAPIPublication
from agnara_http._openapi import _OpenAPIInfo, _project_openapi


def plan(handler: Callable[..., Any], name: str = "target") -> ExecutionPlan:
    return ExecutionPlan.compile(
        CapabilityDefinition(CapabilityId("tests", name), handler), DIRegistry()
    )


def operation(*bindings: _InputBinding, handler: Callable[..., Any]) -> dict[str, Any]:
    document = _project_openapi(
        _compile_exposures(
            (
                _HTTPExposure(
                    "POST",
                    "/thing",
                    plan(handler),
                    bindings,
                    openapi=_OpenAPIPublication(summary="Do it"),
                ),
            )
        ),
        _OpenAPIInfo("Surface API", "1.0"),
    )
    return document["paths"]["/thing"]["post"]


# ---------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------


def test_a_cookie_projects_as_a_cookie_parameter() -> None:
    def handler(session: str) -> None: ...

    projected = operation(_InputBinding("session", _BindingSource.COOKIE), handler=handler)

    assert projected["parameters"] == [
        {"name": "session", "in": "cookie", "required": True, "schema": {"type": "string"}}
    ]
    assert "requestBody" not in projected


def test_an_optional_cookie_is_not_required() -> None:
    def handler(session: str = "anonymous") -> None: ...

    projected = operation(_InputBinding("session", _BindingSource.COOKIE), handler=handler)

    assert projected["parameters"][0]["required"] is False


def test_a_renamed_cookie_projects_its_wire_name() -> None:
    def handler(session: str) -> None: ...

    projected = operation(_InputBinding("session", _BindingSource.COOKIE, "sid"), handler=handler)

    assert projected["parameters"][0]["name"] == "sid"


# ---------------------------------------------------------------------------
# Form fields
# ---------------------------------------------------------------------------


def test_form_fields_project_as_one_request_body_object() -> None:
    """They are properties of a body, not parameters."""

    def handler(email: str, remember: bool = False) -> None: ...

    projected = operation(
        _InputBinding("email", _BindingSource.FORM),
        _InputBinding("remember", _BindingSource.FORM),
        handler=handler,
    )

    assert "parameters" not in projected
    assert projected["requestBody"] == {
        "required": True,
        "content": {
            media: {
                "schema": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"},
                        "remember": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                    "required": ["email"],
                }
            }
            for media in ("application/x-www-form-urlencoded", "multipart/form-data")
        },
    }


def test_a_form_route_advertises_both_encodings_it_accepts() -> None:
    """An HTML form picks the encoding from its enctype; both work."""

    def handler(email: str) -> None: ...

    projected = operation(_InputBinding("email", _BindingSource.FORM), handler=handler)

    assert sorted(projected["requestBody"]["content"]) == [
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    ]


def test_an_all_optional_form_body_is_not_required() -> None:
    def handler(note: str = "") -> None: ...

    projected = operation(_InputBinding("note", _BindingSource.FORM), handler=handler)

    assert projected["requestBody"]["required"] is False
    schema = projected["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert "required" not in schema


def test_a_renamed_form_field_projects_its_wire_name() -> None:
    def handler(email: str) -> None: ...

    projected = operation(
        _InputBinding("email", _BindingSource.FORM, "user-email"), handler=handler
    )

    schema = projected["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert list(schema["properties"]) == ["user-email"]
    assert schema["required"] == ["user-email"]


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def test_an_upload_projects_as_binary_with_an_encoding() -> None:
    """RFC 7578 gives a file part its own content type; OpenAPI puts it in `encoding`."""

    def handler(avatar: bytes) -> None: ...

    projected = operation(_InputBinding("avatar", _BindingSource.UPLOAD), handler=handler)

    assert projected["requestBody"] == {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": {"avatar": {"type": "string", "format": "binary"}},
                    "additionalProperties": False,
                    "required": ["avatar"],
                },
                "encoding": {"avatar": {"contentType": "application/octet-stream"}},
            }
        },
    }


def test_an_upload_route_advertises_multipart_only() -> None:
    """A URL-encoded body cannot carry a file part, so it is not advertised."""

    def handler(avatar: bytes) -> None: ...

    projected = operation(_InputBinding("avatar", _BindingSource.UPLOAD), handler=handler)

    assert list(projected["requestBody"]["content"]) == ["multipart/form-data"]


def test_fields_and_an_upload_share_one_body_schema() -> None:
    def handler(title: str, avatar: bytes) -> None: ...

    projected = operation(
        _InputBinding("title", _BindingSource.FORM),
        _InputBinding("avatar", _BindingSource.UPLOAD),
        handler=handler,
    )
    media = projected["requestBody"]["content"]["multipart/form-data"]

    assert media["schema"]["properties"] == {
        "avatar": {"type": "string", "format": "binary"},
        "title": {"type": "string"},
    }
    assert media["schema"]["required"] == ["avatar", "title"]
    assert list(media["encoding"]) == ["avatar"]


def test_an_upload_never_projects_the_bytes_schema_of_the_input() -> None:
    """`bytes` is `string/format: binary` to the schema port and to OpenAPI alike."""

    def handler(avatar: bytes) -> None: ...

    projected = operation(_InputBinding("avatar", _BindingSource.UPLOAD), handler=handler)
    schema = projected["requestBody"]["content"]["multipart/form-data"]["schema"]

    assert schema["properties"]["avatar"] == {"type": "string", "format": "binary"}


# ---------------------------------------------------------------------------
# Mixing
# ---------------------------------------------------------------------------


def test_every_source_projects_into_its_own_place() -> None:
    def handler(order_id: int, trace: str, session: str, title: str, blob: bytes) -> None: ...

    document = _project_openapi(
        _compile_exposures(
            (
                _HTTPExposure(
                    "POST",
                    "/orders/{order_id}",
                    plan(handler),
                    (
                        _InputBinding("order_id", _BindingSource.PATH),
                        _InputBinding("trace", _BindingSource.HEADER, "x-trace"),
                        _InputBinding("session", _BindingSource.COOKIE),
                        _InputBinding("title", _BindingSource.FORM),
                        _InputBinding("blob", _BindingSource.UPLOAD),
                    ),
                    openapi=_OpenAPIPublication(summary="Everything"),
                ),
            )
        ),
        _OpenAPIInfo("Surface API", "1.0"),
    )
    projected = document["paths"]["/orders/{order_id}"]["post"]

    assert [(item["in"], item["name"]) for item in projected["parameters"]] == [
        ("path", "order_id"),
        ("header", "x-trace"),
        ("cookie", "session"),
    ]
    assert sorted(
        projected["requestBody"]["content"]["multipart/form-data"]["schema"]["properties"]
    ) == ["blob", "title"]


def test_the_projection_stays_deterministic_across_declaration_order() -> None:
    def handler(alpha: str, omega: str) -> None: ...

    forward = operation(
        _InputBinding("alpha", _BindingSource.FORM),
        _InputBinding("omega", _BindingSource.FORM),
        handler=handler,
    )
    backward = operation(
        _InputBinding("omega", _BindingSource.FORM),
        _InputBinding("alpha", _BindingSource.FORM),
        handler=handler,
    )

    assert forward["requestBody"] == backward["requestBody"]


@pytest.mark.parametrize("source", [_BindingSource.FORM, _BindingSource.UPLOAD])
def test_an_unpublished_exposure_projects_no_body(source: _BindingSource) -> None:
    """ADR 0035: publication is per exposure, and these are no exception."""

    def handler(value: bytes) -> None: ...

    document = _project_openapi(
        _compile_exposures(
            (_HTTPExposure("POST", "/thing", plan(handler), (_InputBinding("value", source),)),)
        ),
        _OpenAPIInfo("Surface API", "1.0"),
    )

    assert document["paths"] == {}
