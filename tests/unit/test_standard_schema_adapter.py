"""E2.2 — recursive standard-library schema compositions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from enum import Enum, IntEnum, StrEnum
from typing import Any, Literal

import pytest

from agnara import SchemaError, StandardSchemaAdapter, TypeSchema, ValidationError
from agnara.schema import (
    DictionarySchema,
    EnumSchema,
    ListSchema,
    LiteralSchema,
    TupleSchema,
    UnionSchema,
)


class Colour(StrEnum):
    RED = "red"
    BLUE = "blue"


class Priority(IntEnum):
    LOW = 1
    HIGH = 2


class Mixed(Enum):
    NONE = None
    NAME = "name"


@pytest.fixture
def adapter() -> StandardSchemaAdapter:
    return StandardSchemaAdapter()


class TestCompositeCompilation:
    @pytest.mark.parametrize(
        ("annotation", "schema_type"),
        [
            (list[int], ListSchema),
            (dict[str, int], DictionarySchema),
            (tuple[int, str], TupleSchema),
            (tuple[int, ...], TupleSchema),
            (int | str, UnionSchema),
            (Literal["open", "closed"], LiteralSchema),
            (Colour, EnumSchema),
        ],
    )
    def test_compiles_each_supported_composition(
        self,
        adapter: StandardSchemaAdapter,
        annotation: Any,
        schema_type: type,
    ) -> None:
        schema = adapter.compile(annotation)
        assert isinstance(schema, schema_type)
        assert isinstance(schema, TypeSchema)

    def test_compiles_nested_annotations(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(dict[str, list[tuple[int, str | None]]])
        value = {"items": [(1, "one"), (2, None)]}
        assert schema.validate(value) is value

    def test_compiles_an_empty_fixed_tuple(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(tuple[()])
        assert schema.validate(()) == ()


class TestContainerValidation:
    @pytest.mark.parametrize(
        ("annotation", "value"),
        [
            (list[int], [1, 2]),
            (dict[str, int], {"one": 1}),
            (tuple[int, str], (1, "one")),
            (tuple[int, ...], (1, 2, 3)),
        ],
    )
    def test_accepts_exact_container_types(
        self, adapter: StandardSchemaAdapter, annotation: Any, value: object
    ) -> None:
        assert adapter.compile(annotation).validate(value) is value

    @pytest.mark.parametrize(
        ("annotation", "value", "message"),
        [
            (list[int], (1, 2), "expected list, got tuple"),
            (dict[str, int], [("one", 1)], "expected dict, got list"),
            (tuple[int, str], [1, "one"], "expected tuple, got list"),
        ],
    )
    def test_rejects_lookalike_container_types(
        self,
        adapter: StandardSchemaAdapter,
        annotation: Any,
        value: object,
        message: str,
    ) -> None:
        with pytest.raises(ValidationError, match=message):
            adapter.compile(annotation).validate(value)

    def test_rejects_a_wrong_fixed_tuple_length(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError, match="expected tuple of length 2"):
            adapter.compile(tuple[int, str]).validate((1,))

    def test_rejects_a_non_string_dictionary_key(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError, match="expected str key") as caught:
            adapter.compile(dict[str, int]).validate({1: 1})
        assert caught.value.path == ("<key>",)


class TestNestedPaths:
    def test_list_reports_the_failing_index(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError) as caught:
            adapter.compile(list[int]).validate([1, "two"])
        assert caught.value.path == (1,)
        assert caught.value.location == "[1]"

    def test_dictionary_reports_the_failing_key(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError) as caught:
            adapter.compile(dict[str, int]).validate({"count": "two"})
        assert caught.value.path == ("count",)

    def test_tuple_reports_the_failing_index(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError) as caught:
            adapter.compile(tuple[str, int]).validate(("one", "two"))
        assert caught.value.path == (1,)

    def test_paths_accumulate_through_compositions(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(dict[str, list[tuple[int, str]]])
        with pytest.raises(ValidationError) as caught:
            schema.validate({"rows": [(1, "ok"), (2, 3)]})
        assert caught.value.path == ("rows", 1, 1)
        assert caught.value.location == "rows[1][1]"

    def test_union_preserves_the_most_specific_nested_path(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        schema = adapter.compile(list[int] | dict[str, int])
        with pytest.raises(ValidationError) as caught:
            schema.validate([1, "two"])
        assert caught.value.path == (1,)


class TestUnionsAndLiterals:
    @pytest.mark.parametrize("value", [1, "one"])
    def test_union_accepts_each_member(self, adapter: StandardSchemaAdapter, value: object) -> None:
        assert adapter.compile(int | str).validate(value) is value

    def test_optional_accepts_none(self, adapter: StandardSchemaAdapter) -> None:
        assert adapter.compile(int | None).validate(None) is None

    def test_union_reports_every_member_failure(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError, match="does not match any union member") as caught:
            adapter.compile(int | str).validate(False)
        assert "expected int" in str(caught.value)
        assert "expected str" in str(caught.value)

    @pytest.mark.parametrize("value", ["open", "closed"])
    def test_literal_accepts_each_exact_value(
        self, adapter: StandardSchemaAdapter, value: str
    ) -> None:
        assert adapter.compile(Literal["open", "closed"]).validate(value) is value

    def test_literal_does_not_confuse_bool_and_int(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError):
            adapter.compile(Literal[1]).validate(True)


class TestEnums:
    @pytest.mark.parametrize("enum_type", [Colour, Priority, Mixed])
    def test_accepts_an_exact_enum_member(
        self, adapter: StandardSchemaAdapter, enum_type: type[Enum]
    ) -> None:
        member = next(iter(enum_type))
        assert adapter.compile(enum_type).validate(member) is member

    def test_rejects_the_underlying_value(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(ValidationError, match="expected Colour, got str"):
            adapter.compile(Colour).validate("red")

    def test_rejects_an_empty_enum_at_compile_time(self, adapter: StandardSchemaAdapter) -> None:
        class Empty(Enum):
            pass

        with pytest.raises(SchemaError, match="at least one member"):
            adapter.compile(Empty)

    def test_rejects_non_json_enum_values_at_compile_time(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        class Bad(Enum):
            VALUE = object()

        with pytest.raises(SchemaError, match="JSON scalar"):
            adapter.compile(Bad)


class TestJsonSchema:
    @pytest.mark.parametrize(
        ("annotation", "expected"),
        [
            (list[int], {"type": "array", "items": {"type": "integer"}}),
            (
                dict[str, int],
                {"type": "object", "additionalProperties": {"type": "integer"}},
            ),
            (
                tuple[int, str],
                {
                    "type": "array",
                    "prefixItems": [{"type": "integer"}, {"type": "string"}],
                    "items": False,
                    "minItems": 2,
                    "maxItems": 2,
                },
            ),
            (tuple[int, ...], {"type": "array", "items": {"type": "integer"}}),
            (
                int | None,
                {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            ),
            (Literal["open"], {"const": "open"}),
            (Literal["open", "closed"], {"enum": ["open", "closed"]}),
            (Colour, {"enum": ["red", "blue"], "type": "string"}),
            (Priority, {"enum": [1, 2], "type": "integer"}),
            (Mixed, {"enum": [None, "name"]}),
        ],
    )
    def test_generates_deterministic_plain_fragments(
        self,
        adapter: StandardSchemaAdapter,
        annotation: Any,
        expected: dict[str, Any],
    ) -> None:
        assert adapter.compile(annotation).json_schema() == expected

    def test_nested_fragments_are_fresh(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(list[dict[str, int]])
        first = dict(schema.json_schema())
        first["items"] = {}
        assert schema.json_schema()["items"] == {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        }

    @pytest.mark.parametrize(
        "annotation",
        [list[int], dict[str, int], tuple[int, str], int | str, Literal[1], Colour],
    )
    def test_fragment_does_not_declare_a_dialect(
        self, adapter: StandardSchemaAdapter, annotation: Any
    ) -> None:
        assert "$schema" not in adapter.compile(annotation).json_schema()


class TestUnsupportedAnnotations:
    @pytest.mark.parametrize(
        "annotation",
        [list, dict, tuple, set[int], frozenset[int], dict[int, str], list[complex]],
    )
    def test_rejects_unsupported_or_incomplete_compositions(
        self, adapter: StandardSchemaAdapter, annotation: Any
    ) -> None:
        with pytest.raises(SchemaError):
            adapter.compile(annotation)

    def test_rejects_a_non_json_literal_value(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(SchemaError, match="JSON-compatible"):
            adapter.compile(Literal[b"bytes"])

    @pytest.mark.parametrize("value", [float("inf"), float("nan")])
    def test_rejects_a_non_finite_enum_value(
        self, adapter: StandardSchemaAdapter, value: float
    ) -> None:
        class NonFinite(Enum):
            VALUE = value

        with pytest.raises(SchemaError, match="finite JSON scalar"):
            adapter.compile(NonFinite)

    def test_dictionary_key_error_is_actionable(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(SchemaError, match="keys must be str"):
            adapter.compile(dict[int, str])


class TestSupportsAndImmutability:
    @pytest.mark.parametrize(
        "annotation",
        [list[int], dict[str, list[int]], tuple[int, ...], int | str, Literal[1], Colour],
    )
    def test_supports_every_compilable_composition(
        self, adapter: StandardSchemaAdapter, annotation: Any
    ) -> None:
        assert adapter.supports(annotation)

    @pytest.mark.parametrize(
        "annotation", [list, dict[int, str], list[complex], set[int], Literal[b"x"]]
    )
    def test_does_not_support_annotations_compile_would_reject(
        self, adapter: StandardSchemaAdapter, annotation: Any
    ) -> None:
        assert not adapter.supports(annotation)

    @pytest.mark.parametrize(
        "annotation",
        [list[int], dict[str, int], tuple[int, str], int | str, Literal[1], Colour],
    )
    def test_compiled_compositions_are_frozen(
        self, adapter: StandardSchemaAdapter, annotation: Any
    ) -> None:
        schema = adapter.compile(annotation)
        with pytest.raises(FrozenInstanceError):
            schema.changed = True  # ty: ignore[unresolved-attribute]
