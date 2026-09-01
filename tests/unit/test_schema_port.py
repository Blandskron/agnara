"""E2.1 and E2.4 — the schema port and its standard-library adapter."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import NoneType
from typing import Any

import pytest

from agnara import (
    SchemaAdapter,
    SchemaError,
    StandardSchemaAdapter,
    TypeSchema,
    ValidationError,
)
from agnara.schema import AnySchema, NoneSchema, PrimitiveSchema

PRIMITIVES = [bool, int, float, str, bytes]

SAMPLES: dict[type, object] = {
    bool: True,
    int: 3,
    float: 3.5,
    str: "text",
    bytes: b"bytes",
}


@pytest.fixture
def adapter() -> StandardSchemaAdapter:
    return StandardSchemaAdapter()


class TestPortConformance:
    def test_the_adapter_satisfies_the_port_structurally(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        """A msgspec or Pydantic bridge must not need to inherit from us."""
        assert isinstance(adapter, SchemaAdapter)

    @pytest.mark.parametrize("annotation", [*PRIMITIVES, None, Any])
    def test_every_compiled_schema_satisfies_the_port(
        self, adapter: StandardSchemaAdapter, annotation: Any
    ) -> None:
        assert isinstance(adapter.compile(annotation), TypeSchema)

    def test_a_foreign_implementation_satisfies_the_port(self) -> None:
        """Nothing about the port requires an Agnara base class."""

        class Foreign:
            def validate(self, value: object) -> Any:
                return value

            def json_schema(self) -> dict[str, Any]:
                return {}

        assert isinstance(Foreign(), TypeSchema)


class TestCompilation:
    @pytest.mark.parametrize("annotation", PRIMITIVES)
    def test_compiles_each_primitive(
        self, adapter: StandardSchemaAdapter, annotation: type
    ) -> None:
        assert isinstance(adapter.compile(annotation), PrimitiveSchema)

    def test_compiles_none(self, adapter: StandardSchemaAdapter) -> None:
        assert isinstance(adapter.compile(None), NoneSchema)

    def test_compiles_the_none_type(self, adapter: StandardSchemaAdapter) -> None:
        """`-> None` reaches introspection as `NoneType`, not `None`."""
        assert isinstance(adapter.compile(NoneType), NoneSchema)

    def test_compiles_any(self, adapter: StandardSchemaAdapter) -> None:
        assert isinstance(adapter.compile(Any), AnySchema)

    @pytest.mark.parametrize("annotation", [list, dict, set, tuple, complex])
    def test_rejects_an_unsupported_annotation(
        self, adapter: StandardSchemaAdapter, annotation: Any
    ) -> None:
        """Failing at compile time is the point: an unsupported annotation is
        a startup failure, not a surprise on first invocation (ADR 0005)."""
        with pytest.raises(SchemaError):
            adapter.compile(annotation)

    def test_the_error_names_the_annotation_and_what_is_supported(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        with pytest.raises(SchemaError, match="list is not supported") as caught:
            adapter.compile(list)
        assert "int" in str(caught.value)

    def test_rejects_an_arbitrary_object(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(SchemaError):
            adapter.compile(object())


class TestSupports:
    @pytest.mark.parametrize("annotation", [*PRIMITIVES, None, NoneType, Any])
    def test_reports_true_for_supported(
        self, adapter: StandardSchemaAdapter, annotation: Any
    ) -> None:
        assert adapter.supports(annotation)

    @pytest.mark.parametrize("annotation", [list, dict, complex, object()])
    def test_reports_false_for_unsupported(
        self, adapter: StandardSchemaAdapter, annotation: Any
    ) -> None:
        assert not adapter.supports(annotation)

    @pytest.mark.parametrize("annotation", [*PRIMITIVES, None, Any, list, dict, complex])
    def test_agrees_with_compile(self, adapter: StandardSchemaAdapter, annotation: Any) -> None:
        """`supports` must not disagree with what `compile` actually does."""
        try:
            adapter.compile(annotation)
        except SchemaError:
            assert not adapter.supports(annotation)
        else:
            assert adapter.supports(annotation)


class TestValidation:
    @pytest.mark.parametrize("annotation", PRIMITIVES)
    def test_accepts_a_matching_value(
        self, adapter: StandardSchemaAdapter, annotation: type
    ) -> None:
        value = SAMPLES[annotation]
        assert adapter.compile(annotation).validate(value) == value

    def test_returns_the_same_object(self, adapter: StandardSchemaAdapter) -> None:
        value = "text"
        assert adapter.compile(str).validate(value) is value

    def test_rejects_a_mismatched_value(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError, match="expected int, got str"):
            adapter.compile(int).validate("3")

    def test_does_not_coerce(self, adapter: StandardSchemaAdapter) -> None:
        """The port permits coercion; this adapter declines it.

        A transport knows its wire format and can convert before validating.
        A direct Python call has no wire format, so silently accepting "3"
        for an int would hide a real bug.
        """
        with pytest.raises(ValidationError):
            adapter.compile(int).validate("3")

    def test_none_accepts_none(self, adapter: StandardSchemaAdapter) -> None:
        assert adapter.compile(None).validate(None) is None

    def test_none_rejects_a_value(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError, match="expected None, got int"):
            adapter.compile(None).validate(0)

    def test_any_accepts_anything(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(Any)
        for value in (None, 0, "text", [1], object()):
            assert schema.validate(value) is value


class TestBoolIsNotInt:
    """`isinstance(True, int)` is true in Python. A schema must not agree."""

    def test_a_bool_does_not_satisfy_int(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError, match="expected int, got bool"):
            adapter.compile(int).validate(True)

    def test_a_bool_does_not_satisfy_float(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError, match="expected float, got bool"):
            adapter.compile(float).validate(False)

    def test_an_int_does_not_satisfy_bool(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError, match="expected bool, got int"):
            adapter.compile(bool).validate(1)

    def test_an_int_does_not_satisfy_float(self, adapter: StandardSchemaAdapter) -> None:
        """No numeric tower either: `3` is not a `float` here."""
        with pytest.raises(ValidationError, match="expected float, got int"):
            adapter.compile(float).validate(3)

    def test_a_str_subclass_does_not_satisfy_str(self, adapter: StandardSchemaAdapter) -> None:
        class Slug(str): ...

        with pytest.raises(ValidationError):
            adapter.compile(str).validate(Slug("x"))


class TestJsonSchema:
    @pytest.mark.parametrize(
        ("annotation", "expected"),
        [
            (bool, {"type": "boolean"}),
            (int, {"type": "integer"}),
            (float, {"type": "number"}),
            (str, {"type": "string"}),
            (None, {"type": "null"}),
        ],
    )
    def test_maps_to_the_json_type(
        self, adapter: StandardSchemaAdapter, annotation: Any, expected: dict[str, Any]
    ) -> None:
        assert adapter.compile(annotation).json_schema() == expected

    def test_bytes_is_a_binary_string(self, adapter: StandardSchemaAdapter) -> None:
        """`bytes` has no JSON type; OpenAPI's convention is a binary string."""
        assert adapter.compile(bytes).json_schema() == {"type": "string", "format": "binary"}

    def test_any_is_the_empty_schema(self, adapter: StandardSchemaAdapter) -> None:
        assert adapter.compile(Any).json_schema() == {}

    def test_declares_no_dialect(self, adapter: StandardSchemaAdapter) -> None:
        """Which dialect applies is a property of the assembled document, not
        of one field. Emitting `$schema` here would put a protocol concern in
        the kernel (PRINCIPLES.md P3)."""
        for annotation in (*PRIMITIVES, None, Any):
            assert "$schema" not in adapter.compile(annotation).json_schema()

    def test_returns_plain_data(self, adapter: StandardSchemaAdapter) -> None:
        """No framework type may leak into a generated document."""
        schema = adapter.compile(int).json_schema()
        assert type(schema) is dict
        assert all(type(key) is str for key in schema)


class TestImmutability:
    @pytest.mark.parametrize("annotation", [int, None, Any])
    def test_compiled_schemas_are_frozen(
        self, adapter: StandardSchemaAdapter, annotation: Any
    ) -> None:
        """Frozen so the compiled registry stays shareable after startup."""
        schema = adapter.compile(annotation)
        with pytest.raises(FrozenInstanceError):
            schema.python_type = str  # ty: ignore[unresolved-attribute]

    def test_equal_schemas_compare_equal(self, adapter: StandardSchemaAdapter) -> None:
        assert adapter.compile(int) == adapter.compile(int)

    def test_different_schemas_compare_unequal(self, adapter: StandardSchemaAdapter) -> None:
        assert adapter.compile(int) != adapter.compile(str)

    def test_mutating_a_returned_json_schema_does_not_affect_the_next_call(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        """Each call builds a fresh mapping, so a caller editing one document
        cannot corrupt every later one."""
        schema = adapter.compile(int)
        first = schema.json_schema()
        dict(first).clear()
        assert schema.json_schema() == {"type": "integer"}


class TestValidationErrorPaths:
    def test_a_top_level_failure_has_no_path(self) -> None:
        error = ValidationError("bad")
        assert error.path == ()
        assert error.location == "<value>"

    def test_at_pushes_a_segment_outward(self) -> None:
        error = ValidationError("bad").at("field")
        assert error.path == ("field",)
        assert error.location == "field"

    def test_segments_accumulate_outermost_last(self) -> None:
        """A nested validator raises against the value it was handed; each
        caller adds the segment that value came from as the error travels
        outward."""
        error = ValidationError("expected int, got str").at("items").at(2).at("order")
        assert error.path == ("order", 2, "items")

    def test_renders_indices_in_brackets(self) -> None:
        error = ValidationError("bad").at("items").at(2).at("order")
        assert error.location == "order[2].items"

    def test_a_leading_index_needs_no_dot(self) -> None:
        assert ValidationError("bad").at(0).location == "[0]"

    def test_str_includes_the_location_and_message(self) -> None:
        assert str(ValidationError("bad").at("field")) == "field: bad"

    def test_at_does_not_mutate_the_original(self) -> None:
        original = ValidationError("bad")
        original.at("field")
        assert original.path == ()

    def test_is_protocol_neutral(self) -> None:
        """No status code, no problem document, no JSON-RPC error object."""
        error = ValidationError("bad").at("field")
        forbidden = {"status_code", "status", "http_status", "code", "to_problem"}
        assert forbidden.isdisjoint(dir(error))
