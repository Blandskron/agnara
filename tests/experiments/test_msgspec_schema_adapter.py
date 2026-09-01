"""E2.5 — executable evidence for the isolated msgspec adapter prototype."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

import msgspec
import pytest
from experiments.msgspec_schema_adapter import MsgspecSchemaAdapter

from agnara import SchemaAdapter, SchemaError, TypeSchema, ValidationError


class Address(msgspec.Struct, frozen=True):
    city: str


class User(msgspec.Struct, frozen=True):
    name: str
    addresses: list[Address]


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@pytest.fixture
def adapter() -> MsgspecSchemaAdapter:
    return MsgspecSchemaAdapter()


class TestPortConformance:
    def test_adapter_satisfies_the_port_structurally(self, adapter: MsgspecSchemaAdapter) -> None:
        assert isinstance(adapter, SchemaAdapter)

    @pytest.mark.parametrize("annotation", [int, list[str], User, Point])
    def test_compiled_schemas_satisfy_the_port(
        self, adapter: MsgspecSchemaAdapter, annotation: Any
    ) -> None:
        assert isinstance(adapter.compile(annotation), TypeSchema)

    def test_compiled_schema_is_immutable(self, adapter: MsgspecSchemaAdapter) -> None:
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
            Annotated[int, msgspec.Meta(ge=0)],
            User,
            Point,
        ],
    )
    def test_accepts_representative_msgspec_types(
        self, adapter: MsgspecSchemaAdapter, annotation: Any
    ) -> None:
        assert adapter.supports(annotation)

    def test_rejects_an_unsupported_annotation_at_compile_time(
        self, adapter: MsgspecSchemaAdapter
    ) -> None:
        with pytest.raises(SchemaError, match="complex is not supported"):
            adapter.compile(complex)

    def test_supports_agrees_with_compile(self, adapter: MsgspecSchemaAdapter) -> None:
        assert adapter.supports(User)
        assert not adapter.supports(complex)


class TestValidation:
    def test_strict_mode_rejects_unsafe_string_coercion(
        self, adapter: MsgspecSchemaAdapter
    ) -> None:
        with pytest.raises(ValidationError, match="Expected `int`, got `str`"):
            adapter.compile(int).validate("3")

    def test_constructs_a_nested_struct_from_builtins(self, adapter: MsgspecSchemaAdapter) -> None:
        value = {"name": "Ada", "addresses": [{"city": "Santiago"}]}
        assert adapter.compile(User).validate(value) == User("Ada", [Address("Santiago")])

    def test_constructs_a_dataclass_from_builtins(self, adapter: MsgspecSchemaAdapter) -> None:
        assert adapter.compile(Point).validate({"x": 2, "y": 3}) == Point(2, 3)

    def test_preserves_an_existing_typed_instance(self, adapter: MsgspecSchemaAdapter) -> None:
        value = User("Ada", [Address("Santiago")])
        assert adapter.compile(User).validate(value) is value

    def test_translates_unambiguous_nested_paths(self, adapter: MsgspecSchemaAdapter) -> None:
        value = {"name": "Ada", "addresses": [{"city": 4}]}
        with pytest.raises(ValidationError) as caught:
            adapter.compile(User).validate(value)
        assert caught.value.path == ("addresses", 0, "city")
        assert caught.value.message == "Expected `str`, got `int`"

    def test_retains_ambiguous_dictionary_location_in_message(
        self, adapter: MsgspecSchemaAdapter
    ) -> None:
        with pytest.raises(ValidationError) as caught:
            adapter.compile(dict[str, list[str]]).validate({"groups": ["ok", 1]})
        assert caught.value.path == ()
        assert "`$[...][1]`" in caught.value.message


class TestJsonSchema:
    def test_exports_msgspec_constraints(self, adapter: MsgspecSchemaAdapter) -> None:
        annotation = Annotated[int, msgspec.Meta(ge=0, description="A count")]
        assert adapter.compile(annotation).json_schema() == {
            "type": "integer",
            "minimum": 0,
            "description": "A count",
        }

    def test_exports_nested_struct_definitions(self, adapter: MsgspecSchemaAdapter) -> None:
        schema = adapter.compile(User).json_schema()
        assert schema["$ref"] == "#/$defs/User"
        assert schema["$defs"]["User"]["properties"]["addresses"]["items"] == {
            "$ref": "#/$defs/Address"
        }

    def test_returns_fresh_plain_data(self, adapter: MsgspecSchemaAdapter) -> None:
        compiled = adapter.compile(list[int])
        first = compiled.json_schema()
        first["items"]["type"] = "string"
        assert compiled.json_schema() == {"type": "array", "items": {"type": "integer"}}

    def test_does_not_declare_a_dialect(self, adapter: MsgspecSchemaAdapter) -> None:
        assert "$schema" not in adapter.compile(User).json_schema()
