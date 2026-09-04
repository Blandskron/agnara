"""Deterministic OpenAPI 3.2 projection from compiled HTTP exposures (E6.7)."""

import json
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara.schema import SchemaAdapter
from agnara_http._binding import _BindingDefinitionError, _BindingSource, _InputBinding
from agnara_http._dispatch import (
    _compile_exposures,
    _HTTPExposure,
    _OpenAPIPublication,
)
from agnara_http._openapi import (
    _OpenAPIDefinitionError,
    _OpenAPIInfo,
    _project_openapi,
    _serialize_openapi,
)


def plan(
    handler: Callable[..., Any],
    name: str = "target",
    *,
    description: str | None = None,
    schema_adapter: SchemaAdapter | None = None,
) -> ExecutionPlan:
    return ExecutionPlan.compile(
        CapabilityDefinition(
            CapabilityId("tests", name),
            handler,
            description=description,
        ),
        DIRegistry(),
        schema_adapter=schema_adapter,
    )


def project(*exposures: _HTTPExposure) -> dict[str, Any]:
    return _project_openapi(
        _compile_exposures(exposures),
        _OpenAPIInfo("Orders API", "2026-09-03"),
    )


def test_projects_compiled_bindings_and_explicit_metadata() -> None:
    def create(
        order_id: int,
        token: str,
        command: dict[str, int],
        search: str = "all",
    ) -> dict[str, int]:
        del token, command, search
        return {"order_id": order_id}

    document = project(
        _HTTPExposure(
            "POST",
            "/orders/{order_id}",
            plan(create, "create", description="Create one order."),
            (
                _InputBinding("order_id", _BindingSource.PATH),
                _InputBinding("search", _BindingSource.QUERY, "q"),
                _InputBinding("token", _BindingSource.HEADER, "x-token"),
                _InputBinding("command", _BindingSource.BODY),
            ),
            openapi=_OpenAPIPublication(
                summary="Create order",
                publish_description=True,
                tags=("orders",),
                deprecated=True,
            ),
        )
    )

    assert document["openapi"] == "3.2.0"
    assert document["jsonSchemaDialect"] == "https://spec.openapis.org/oas/3.1/dialect/base"
    assert document["info"] == {"title": "Orders API", "version": "2026-09-03"}
    operation = document["paths"]["/orders/{order_id}"]["post"]
    assert operation["operationId"] == "tests.create:post:/orders/{order_id}"
    assert operation["summary"] == "Create order"
    assert operation["description"] == "Create one order."
    assert operation["tags"] == ["orders"]
    assert operation["deprecated"] is True
    assert operation["parameters"] == [
        {
            "name": "order_id",
            "in": "path",
            "required": True,
            "schema": {"type": "integer"},
        },
        {
            "name": "q",
            "in": "query",
            "required": False,
            "schema": {"type": "string"},
        },
        {
            "name": "x-token",
            "in": "header",
            "required": True,
            "schema": {"type": "string"},
        },
    ]
    assert operation["requestBody"] == {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"type": "object", "additionalProperties": {"type": "integer"}}
            }
        },
    }


def test_describes_the_implemented_success_and_problem_boundaries() -> None:
    def ping() -> str:
        return "pong"

    operation = project(_HTTPExposure("GET", "/ping", plan(ping), openapi=_OpenAPIPublication()))[
        "paths"
    ]["/ping"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {}
    assert operation["responses"]["204"] == {
        "description": "Successful capability result with no value."
    }
    assert operation["responses"]["default"]["content"]["application/problem+json"] == {
        "schema": {"$ref": "#/components/schemas/Problem"}
    }


def test_problem_component_has_the_wire_members_both_failure_paths_share() -> None:
    document = project()

    schema = document["components"]["schemas"]["Problem"]
    assert schema["required"] == ["type", "title", "status", "code", "detail"]
    assert set(schema["properties"]) == {
        "type",
        "title",
        "status",
        "code",
        "detail",
        "details",
        "instance",
    }


def test_unpublished_exposure_contributes_nothing_to_the_document() -> None:
    def hidden(secret: str) -> str:
        return secret

    routes = _compile_exposures(
        [
            _HTTPExposure(
                "GET",
                "/private/{secret}",
                plan(hidden, "internal_secret", description="credential-in-description"),
                (_InputBinding("secret", _BindingSource.PATH),),
            )
        ]
    )
    encoded = _serialize_openapi(_project_openapi(routes, _OpenAPIInfo("API", "1")))

    assert json.loads(encoded)["paths"] == {}
    assert b"private" not in encoded
    assert b"internal_secret" not in encoded
    assert b"credential-in-description" not in encoded


def test_capability_description_requires_separate_publication_consent() -> None:
    def ping() -> str:
        return "pong"

    operation = project(
        _HTTPExposure(
            "GET",
            "/ping",
            plan(ping, description="not explicitly public"),
            openapi=_OpenAPIPublication(),
        )
    )["paths"]["/ping"]["get"]

    assert "description" not in operation


def test_one_capability_with_two_exposures_gets_unique_stable_operation_ids() -> None:
    def ping() -> str:
        return "pong"

    compiled = plan(ping)
    document = project(
        _HTTPExposure("GET", "/ping", compiled, openapi=_OpenAPIPublication()),
        _HTTPExposure("HEAD", "/ping", compiled, openapi=_OpenAPIPublication()),
    )

    assert document["paths"]["/ping"]["get"]["operationId"] == "tests.target:get:/ping"
    assert document["paths"]["/ping"]["head"]["operationId"] == "tests.target:head:/ping"
    assert "content" not in document["paths"]["/ping"]["head"]["responses"]["200"]


@pytest.mark.parametrize("header", ["accept", "authorization", "content-type"])
def test_a_reserved_header_binding_is_not_misrepresented_as_a_parameter(header: str) -> None:
    def show(value: str) -> str:
        return value

    routes = _compile_exposures(
        [
            _HTTPExposure(
                "GET",
                "/show",
                plan(show),
                (_InputBinding("value", _BindingSource.HEADER, header),),
                openapi=_OpenAPIPublication(),
            )
        ]
    )

    with pytest.raises(_OpenAPIDefinitionError, match="cannot be represented"):
        _project_openapi(routes, _OpenAPIInfo("API", "1"))


def test_serialization_is_byte_identical_and_compact() -> None:
    def ping() -> str:
        return "pong"

    routes = _compile_exposures(
        [_HTTPExposure("GET", "/ping", plan(ping), openapi=_OpenAPIPublication())]
    )
    info = _OpenAPIInfo("Ágnara API", "1", summary="Résumé")

    first = _serialize_openapi(_project_openapi(routes, info))
    second = _serialize_openapi(_project_openapi(routes, info))

    assert first == second
    assert b"\n" not in first
    assert "Ágnara API" in first.decode("utf-8")
    assert json.loads(first)["info"]["summary"] == "Résumé"


@pytest.mark.parametrize("method", ["CONNECT", "CUSTOM"])
def test_a_published_unrepresentable_method_fails(method: str) -> None:
    def ping() -> str:
        return "pong"

    routes = _compile_exposures(
        [_HTTPExposure(method, "/ping", plan(ping), openapi=_OpenAPIPublication())]
    )

    with pytest.raises(_OpenAPIDefinitionError, match=r"no OpenAPI 3\.2 Path Item field"):
        _project_openapi(routes, _OpenAPIInfo("API", "1"))


def test_an_unpublished_unrepresentable_method_is_filtered_before_validation() -> None:
    def ping() -> str:
        return "pong"

    routes = _compile_exposures([_HTTPExposure("CUSTOM", "/secret path", plan(ping))])

    assert _project_openapi(routes, _OpenAPIInfo("API", "1"))["paths"] == {}


@pytest.mark.parametrize("path", ["/secret path", "/bad%2", "/trailing/"])
def test_a_published_non_openapi_path_fails(path: str) -> None:
    def ping() -> str:
        return "pong"

    routes = _compile_exposures(
        [_HTTPExposure("GET", path, plan(ping), openapi=_OpenAPIPublication())]
    )

    with pytest.raises(_OpenAPIDefinitionError, match=r"not an OpenAPI 3\.2 path template"):
        _project_openapi(routes, _OpenAPIInfo("API", "1"))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"title": "", "version": "1"}, "title"),
        ({"title": "API", "version": " "}, "version"),
        ({"title": "API", "version": "1", "summary": ""}, "summary"),
        ({"title": "API", "version": "1", "description": " "}, "description"),
    ],
)
def test_invalid_info_fails_at_definition(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(_OpenAPIDefinitionError, match=message):
        _OpenAPIInfo(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"summary": ""}, "summary"),
        ({"publish_description": 1}, "publish_description"),
        ({"tags": ["orders"]}, "tags must be a tuple"),
        ({"tags": ("orders", "orders")}, "tags must be unique"),
        ({"tags": ("",)}, "non-empty strings"),
        ({"deprecated": 1}, "deprecated"),
    ],
)
def test_invalid_publication_metadata_fails(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(_BindingDefinitionError, match=message):
        _OpenAPIPublication(**kwargs)


def test_exposure_rejects_an_invalid_publication_value_at_compilation() -> None:
    def ping() -> str:
        return "pong"

    exposure = _HTTPExposure(
        "GET",
        "/ping",
        plan(ping),
        openapi=object(),  # ty: ignore[invalid-argument-type]
    )

    with pytest.raises(_BindingDefinitionError, match="openapi must"):
        _compile_exposures([exposure])


class _Schema:
    def __init__(self, fragment: Mapping[str, Any]) -> None:
        self.fragment = fragment

    def validate(self, value: object) -> Any:
        return value

    def json_schema(self) -> Mapping[str, Any]:
        return self.fragment


class _Adapter:
    def __init__(self, fragment: Mapping[str, Any]) -> None:
        self.fragment = fragment

    def supports(self, annotation: Any) -> bool:
        del annotation
        return True

    def compile(self, annotation: Any) -> _Schema:
        del annotation
        return _Schema(self.fragment)


@pytest.mark.parametrize(
    "fragment",
    [
        {"minimum": float("nan")},
        {"enum": [object()]},
        {1: "non-string key"},
    ],
)
def test_non_json_schema_port_output_fails_before_serialization(
    fragment: Mapping[str, Any],
) -> None:
    def show(value: int) -> int:
        return value

    routes = _compile_exposures(
        [
            _HTTPExposure(
                "GET",
                "/show",
                plan(show, schema_adapter=_Adapter(fragment)),
                (_InputBinding("value", _BindingSource.BODY),),
                openapi=_OpenAPIPublication(),
            )
        ]
    )

    with pytest.raises(_OpenAPIDefinitionError):
        _project_openapi(routes, _OpenAPIInfo("API", "1"))


def test_projection_and_serialization_validate_their_boundaries() -> None:
    with pytest.raises(TypeError, match="routes must be a frozen registry"):
        _project_openapi(
            object(),  # ty: ignore[invalid-argument-type]
            _OpenAPIInfo("API", "1"),
        )
    with pytest.raises(TypeError, match="info must be _OpenAPIInfo"):
        _project_openapi(
            _compile_exposures([]),
            object(),  # ty: ignore[invalid-argument-type]
        )
    with pytest.raises(TypeError, match="document must be a mapping"):
        _serialize_openapi([])  # ty: ignore[invalid-argument-type]
