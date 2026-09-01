"""E2.6 ?" executable evidence for the isolated pydantic adapter prototype."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

import pydantic
import pytest
from experiments.pydantic_schema_adapter import PydanticSchemaAdapter

from agnara import SchemaAdapter, SchemaError, TypeSchema, ValidationError


class Address(pydantic.BaseModel):
    city: str


class User(pydantic.BaseModel):
    name: str
    addresses: list[Address]


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@pytest.fixture
def adapter() -> PydanticSchemaAdapter:
    return PydanticSchemaAdapter()


class TestPortConformance:
    def test_adapter_satisfies_the_port_structurally(self, adapter: PydanticSchemaAdapter) -> None:
        assert isinstance(adapter, SchemaAdapter)

    @pytest.mark.parametrize("annotation", [int, list[str], User, Point])
    def test_compiled_schemas_satisfy_the_port(
        self, adapter: PydanticSchemaAdapter, annotation: Any
    ) -> None:
        assert isinstance(adapter.compile(annotation), TypeSchema)

    def test_compiled_schema_is_immutable(self, adapter: PydanticSchemaAdapter) -> None:
        schema = adapter.compile(int)
        with pytest.raises(AttributeError):
            schema.annotation = str  # ty: ignore[invalid-assignment]


class TestCompilation:
    @pytest.mark.parametrize(
        "annotation",
        [
            int,
            list[str],
            dict[str, int],
            tuple[int, ...],
            int | None,
            Annotated[int, pydantic.Field(ge=0)],
            User,
            Point,
        ],
    )
    def test_accepts_representative_pydantic_types(
        self, adapter: PydanticSchemaAdapter, annotation: Any
    ) -> None:
        assert adapter.supports(annotation)

    def test_rejects_an_unsupported_annotation_at_compile_time(
        self, adapter: PydanticSchemaAdapter
    ) -> None:
        with pytest.raises(SchemaError, match="is not supported by the Pydantic prototype"):
            adapter.compile(type(lambda: None))

    def test_supports_agrees_with_compile(self, adapter: PydanticSchemaAdapter) -> None:
        assert adapter.supports(User)
        assert not adapter.supports(type(lambda: None))


class TestValidation:
    def test_strict_mode_rejects_unsafe_string_coercion(
        self, adapter: PydanticSchemaAdapter
    ) -> None:
        with pytest.raises(ValidationError, match="Input should be a valid integer"):
            adapter.compile(int).validate("3")

    def test_constructs_a_nested_model_from_builtins(self, adapter: PydanticSchemaAdapter) -> None:
        value = {"name": "Ada", "addresses": [{"city": "Santiago"}]}
        expected = User(name="Ada", addresses=[Address(city="Santiago")])
        assert adapter.compile(User).validate(value) == expected

    def test_strict_mode_rejects_dict_for_dataclass(self, adapter: PydanticSchemaAdapter) -> None:
        with pytest.raises(ValidationError, match="Input should be an instance of Point"):
            adapter.compile(Point).validate({"x": 2, "y": 3})

    def test_preserves_an_existing_typed_instance(self, adapter: PydanticSchemaAdapter) -> None:
        value = User(name="Ada", addresses=[Address(city="Santiago")])
        assert adapter.compile(User).validate(value) is value

    def test_translates_unambiguous_nested_paths(self, adapter: PydanticSchemaAdapter) -> None:
        value = {"name": "Ada", "addresses": [{"city": 4}]}
        with pytest.raises(ValidationError) as caught:
            adapter.compile(User).validate(value)
        assert caught.value.path == ("addresses", 0, "city")
        assert caught.value.message == "Input should be a valid string"

    def test_retains_dictionary_location_in_path(
        self, adapter: PydanticSchemaAdapter
    ) -> None:
        with pytest.raises(ValidationError) as caught:
            adapter.compile(dict[str, list[str]]).validate({"groups": ["ok", 1]})
        assert caught.value.path == ("groups", 1)


class TestJsonSchema:
    def test_exports_pydantic_constraints(self, adapter: PydanticSchemaAdapter) -> None:
        annotation = Annotated[int, pydantic.Field(ge=0, description="A count")]
        assert adapter.compile(annotation).json_schema() == {
            "type": "integer",
            "minimum": 0,
            "description": "A count",
            }

    def test_exports_nested_model_definitions(self, adapter: PydanticSchemaAdapter) -> None:
        schema = adapter.compile(User).json_schema()
        assert "$defs" in schema
        assert schema["properties"]["addresses"]["items"] == {
            "$ref": "#/$defs/Address"
        }

    def test_returns_fresh_plain_data(self, adapter: PydanticSchemaAdapter) -> None:
        compiled = adapter.compile(list[int])
        first = compiled.json_schema()
        first["items"]["type"] = "string"
        assert compiled.json_schema()["items"]["type"] == "integer"

    def test_does_not_declare_a_dialect(self, adapter: PydanticSchemaAdapter) -> None:
        assert "$schema" not in adapter.compile(User).json_schema()


