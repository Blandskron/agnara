"""Published output schemas agree with validated complete-result HTTP bodies."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import jsonschema
import pytest

from agnara import Agnara
from agnara.di import DIRegistry, provider
from agnara.execution import Failure, FailureCode, Success
from agnara_http import Http, HttpApplication, HttpDefinitionError, OpenApiInfo, OpenApiOperation
from tests.http.test_public_composition import request


class State(StrEnum):
    PAID = "paid"
    NEW = "new"


@dataclass
class Receipt:
    code: int
    state: State


@dataclass
class Summary:
    receipt: Receipt
    tags: list[str]


def application(output: Any, value: Any, *, method: str = "GET", schema_adapter=None):
    effects: list[str] = []
    app = Agnara("outputs")

    @app.capability(output=output)
    def read() -> str:
        effects.append("handler")
        return value

    http = Http()
    http.route(method, "/value", read, openapi=OpenApiOperation())
    served = http.compile(
        app.compile(),
        openapi=OpenApiInfo("Output contracts", "1"),
        openapi_path="/openapi.json",
        schema_adapter=schema_adapter,
    )
    return served, effects


def response_schema(served: HttpApplication, *, method: str = "get") -> dict[str, Any]:
    return served.openapi()["paths"]["/value"][method]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]


@pytest.mark.parametrize(
    ("annotation", "value", "kind"),
    [
        (int, 7, "integer"),
        (float, 1.5, "number"),
        (bool, True, "boolean"),
        (str, "public value", "string"),
        (list[int], [1, 2], "array"),
        (tuple[int, str], (7, "paid"), "array"),
        (dict[str, int], {"total": 2}, "object"),
        (State, State.PAID, "string"),
        (Receipt, Receipt(7, State.PAID), "object"),
        (Summary, Summary(Receipt(7, State.PAID), ["public"]), "object"),
    ],
)
def test_declared_schemas_match_actual_public_http_bodies(annotation, value, kind) -> None:
    served, effects = application(annotation, value)
    schema = response_schema(served)
    assert schema["type"] == kind
    assert effects == []
    status, _, body = request(served, "GET", "/value")
    assert status == 200 and effects == ["handler"]
    jsonschema.Draft202012Validator(schema).validate(json.loads(body))


def test_any_stays_unconstrained_despite_the_handler_return_annotation() -> None:
    served, effects = application(Any, {"not": "a string"})
    assert response_schema(served) == {}
    assert effects == []
    assert request(served, "GET", "/value")[0] == 200


@pytest.mark.parametrize("value", [7, None])
def test_nullable_contract_preserves_the_200_and_bodyless_204_boundary(value) -> None:
    served, _ = application(int | None, value)
    schema = response_schema(served)
    jsonschema.Draft202012Validator(schema).validate(value)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate("not a declared output")
    status, _, body = request(served, "GET", "/value")
    if value is None:
        assert status == 204 and body == b""
    else:
        assert status == 200
        jsonschema.Draft202012Validator(schema).validate(json.loads(body))
    assert "content" not in served.openapi()["paths"]["/value"]["get"]["responses"]["204"]


def test_null_only_contract_does_not_invent_a_json_null_response() -> None:
    served, _ = application(type(None), None)
    assert response_schema(served) == {"type": "null"}
    assert request(served, "GET", "/value")[::2] == (204, b"")


def test_canonical_success_uses_the_validated_value_contract() -> None:
    served, _ = application(int, Success(7))
    assert response_schema(served) == {"type": "integer"}
    assert request(served, "GET", "/value")[::2] == (200, b"7")


@pytest.mark.parametrize(
    "value", ["secret-output-diagnostic", Failure(FailureCode.FORBIDDEN, "denied")]
)
def test_output_violation_and_explicit_failure_keep_problem_mapping_and_redaction(value) -> None:
    served, _ = application(int, value)
    assert response_schema(served) == {"type": "integer"}
    status, headers, body = request(served, "GET", "/value")
    assert b"application/problem+json" in headers[b"content-type"]
    if isinstance(value, Failure):
        assert status == 403 and json.loads(body)["code"] == "forbidden"
    else:
        assert status == 500 and json.loads(body)["code"] == "internal_failure"
        assert b"secret-output-diagnostic" not in body
    assert served.openapi()["paths"]["/value"]["get"]["responses"]["default"]["content"][
        "application/problem+json"
    ]["schema"] == {"$ref": "#/components/schemas/Problem"}


class CustomOutput:
    pass


class Schema:
    def __init__(self, fragment: Any):
        self.fragment = fragment
        self.reads = 0

    def validate(self, value: object) -> Any:
        return value

    def json_schema(self) -> Any:
        self.reads += 1
        return self.fragment


class Adapter:
    def __init__(self, fragment: Any):
        self.schema = Schema(fragment)

    def supports(self, annotation: Any) -> bool:
        return annotation is CustomOutput

    def compile(self, annotation: Any) -> Schema:
        assert annotation is CustomOutput
        return self.schema


@pytest.mark.parametrize(
    "fragment",
    [[], {1: "bad key"}, {"minimum": float("nan")}, {"enum": [object()]}, {"value": b"secret"}],
)
def test_invalid_output_schema_metadata_fails_when_schema_publication_is_compiled(fragment) -> None:
    with pytest.raises(HttpDefinitionError):
        application(CustomOutput, None, schema_adapter=Adapter(fragment))


def test_cyclic_output_metadata_is_refused_at_publication() -> None:
    fragment: dict[str, Any] = {}
    fragment["cycle"] = fragment
    with pytest.raises(HttpDefinitionError, match="cyclic schema"):
        application(CustomOutput, None, schema_adapter=Adapter(fragment))


@pytest.mark.parametrize("surface", ["hidden", "head", "sse"])
def test_non_body_or_unpublished_surfaces_never_retrieve_output_metadata(surface: str) -> None:
    adapter = Adapter({"private-output-schema": object()})
    app = Agnara("private_outputs")
    effects: list[str] = []
    http = Http()
    if surface == "sse":

        @app.capability(output=CustomOutput, streaming=True)
        async def stream() -> AsyncIterator[object]:
            effects.append("producer")
            yield object()

        http.sse("/value", stream)
    else:

        @app.capability(output=CustomOutput)
        def read() -> object:
            effects.append("handler")
            return object()

        http.route(
            "HEAD" if surface == "head" else "GET",
            "/value",
            read,
            openapi=OpenApiOperation() if surface == "head" else None,
        )
    served = http.compile(
        app.compile(),
        openapi=OpenApiInfo("Private", "1"),
        openapi_path="/openapi.json",
        schema_adapter=adapter,
    )
    document = served.openapi()
    if surface == "head":
        assert "content" not in document["paths"]["/value"]["head"]["responses"]["200"]
    else:
        assert document["paths"] == {}
    assert adapter.schema.reads == 0 and effects == []


def test_response_schema_and_served_bytes_are_detached_from_custom_port_data() -> None:
    fragment: dict[str, Any] = {"type": "integer", "enum": [7]}
    adapter = Adapter(fragment)
    served, effects = application(CustomOutput, 7, schema_adapter=adapter)
    first = served.openapi()
    schema = first["paths"]["/value"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert schema == fragment and schema is not fragment
    before = request(served, "GET", "/openapi.json")[2]
    schema["enum"].append(8)
    assert fragment["enum"] == [7] and response_schema(served)["enum"] == [7]
    fragment["enum"].append(9)
    assert schema["enum"] == [7, 8]
    assert request(served, "GET", "/openapi.json")[2] == before
    assert json.loads(before)["paths"]["/value"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["enum"] == [7]
    assert effects == []


class Store:
    pass


def test_publication_never_acquires_resources_or_substitutes_for_authorization() -> None:
    effects: list[str] = []
    app = Agnara("protected_outputs")
    dependencies = DIRegistry()

    @provider()
    def store() -> Iterator[Store]:
        effects.append("open")
        try:
            yield Store()
        finally:
            effects.append("close")

    dependencies.bind(Store, store)

    @app.capability(output=Receipt, scopes={"read"})
    def read(store: Store) -> Receipt:
        effects.append("handler")
        return Receipt(7, State.PAID)

    http = Http()
    http.get("/value", read, openapi=OpenApiOperation())
    served = http.compile(
        app.compile(),
        dependencies=dependencies,
        openapi=OpenApiInfo("Protected", "1"),
        openapi_path="/openapi.json",
    )
    assert response_schema(served)["type"] == "object"
    assert request(served, "GET", "/openapi.json")[0] == 200
    assert request(served, "GET", "/value")[0] == 403
    assert effects == []
