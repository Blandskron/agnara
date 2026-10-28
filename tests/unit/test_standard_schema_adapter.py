"""E2.2 — recursive standard-library schema compositions."""

from __future__ import annotations

import typing
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
    materialize_json,
    serialize_json,
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
        [
            list,
            dict,
            tuple,
            typing.Tuple,  # noqa: UP006 -- runtime value under validation
            set[int],
            frozenset[int],
            dict[int, str],
            list[complex],
        ],
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


class TestSerializeJson:
    """`serialize_json` is the one output rule every JSON transport shares."""

    def test_projects_dataclasses_enums_mappings_and_sequences(self) -> None:
        from collections import OrderedDict
        from dataclasses import dataclass

        @dataclass(frozen=True, slots=True)
        class Receipt:
            identifier: str
            amounts: tuple[int, ...]
            colour: Colour

        value = OrderedDict(
            receipt=Receipt("r-1", (3, 2), Colour.RED), flags=[True, None, 1.5], name="Ñ"
        )
        assert serialize_json(value) == {
            "receipt": {"identifier": "r-1", "amounts": [3, 2], "colour": "red"},
            "flags": [True, None, 1.5],
            "name": "Ñ",
        }

    def test_string_and_integer_enum_members_become_plain_values(self) -> None:
        projected = serialize_json([Colour.RED, Priority.HIGH])
        assert projected == ["red", Priority.HIGH.value]
        assert type(projected[0]) is str
        assert type(projected[1]) is int

    def test_returns_detached_plain_data(self) -> None:
        source = {"items": [1, 2]}
        projected = serialize_json(source)
        assert projected == source
        assert projected is not source
        assert projected["items"] is not source["items"]

    @pytest.mark.parametrize(
        ("value", "message", "path"),
        [
            (float("nan"), "non-finite float is not JSON", ()),
            ({"n": float("inf")}, "non-finite float is not JSON", ("n",)),
            ({1: "value"}, "JSON object keys must be strings", ()),
            ({"value": object()}, "unsupported output type object", ("value",)),
            ([b"binary"], "unsupported output type bytes", (0,)),
            ({"set"}, "unsupported output type set", ()),
        ],
    )
    def test_rejects_values_outside_json_with_their_location(
        self, value: object, message: str, path: tuple[str | int, ...]
    ) -> None:
        with pytest.raises(ValidationError) as caught:
            serialize_json(value)
        assert caught.value.message == message
        assert caught.value.path == path

    def test_rejects_cycles_but_accepts_shared_values(self) -> None:
        shared = [1]
        assert serialize_json({"a": shared, "b": shared}) == {"a": [1], "b": [1]}
        cyclic: list[Any] = []
        cyclic.append({"nested": cyclic})
        with pytest.raises(ValidationError) as caught:
            serialize_json(cyclic)
        assert caught.value.message == "cyclic output value"
        assert caught.value.path == (0, "nested")

    def test_bounds_output_depth(self) -> None:
        deep: object = None
        for _ in range(128):
            deep = [deep]
        assert serialize_json(deep) is not None
        with pytest.raises(ValidationError, match="deeper than 128 levels"):
            serialize_json([deep])


class TestMaterializeLiterals:
    @pytest.mark.parametrize("value", [1.0, 2.0])
    def test_equivalent_json_number_uses_the_declared_python_type(self, value: float) -> None:
        schema = StandardSchemaAdapter().compile(Literal[1, 2])
        result = schema.validate(materialize_json(schema, value))
        assert result == value
        assert type(result) is int
        with pytest.raises(ValidationError):
            schema.validate(value)

    def test_single_value_literal_materializes_equivalent_number(self) -> None:
        schema = StandardSchemaAdapter().compile(Literal[1])
        assert type(schema.validate(materialize_json(schema, 1.0))) is int

    @pytest.mark.parametrize("value", [1, 1.0])
    def test_existing_exact_numeric_match_is_preserved(self, value: int | float) -> None:
        schema = LiteralSchema((1, 1.0))
        assert schema.validate(materialize_json(schema, value)) is value

    def test_integer_can_match_a_declared_float_value(self) -> None:
        schema = LiteralSchema((1.0,))
        assert type(schema.validate(materialize_json(schema, 1))) is float

    @pytest.mark.parametrize("value", [True, False, 3.0, "1", float("inf"), float("nan")])
    def test_undeclared_values_remain_invalid(self, value: object) -> None:
        schema = StandardSchemaAdapter().compile(Literal[0, 1])
        with pytest.raises(ValidationError):
            schema.validate(materialize_json(schema, value))

    @pytest.mark.parametrize("value", [0, 1, 0.0, 1.0])
    def test_numbers_do_not_match_boolean_literals(self, value: int | float) -> None:
        schema = StandardSchemaAdapter().compile(Literal[True, False])
        with pytest.raises(ValidationError):
            schema.validate(materialize_json(schema, value))

    def test_declared_boolean_stays_boolean_next_to_numeric_literal(self) -> None:
        schema = StandardSchemaAdapter().compile(Literal[1, True])
        assert schema.validate(materialize_json(schema, True)) is True

    def test_unequal_number_falls_back_to_float_union_member(self) -> None:
        schema = StandardSchemaAdapter().compile(Literal[1] | float)
        result = schema.validate(materialize_json(schema, 2.0))
        assert result == 2.0
        assert type(result) is float

    def test_nested_literals_materialize_and_retain_failure_paths(self) -> None:
        schema = StandardSchemaAdapter().compile(list[dict[str, Literal[1]]])
        assert schema.validate(materialize_json(schema, [{"choice": 1.0}])) == [{"choice": 1}]
        with pytest.raises(ValidationError) as caught:
            schema.validate(materialize_json(schema, [{"choice": 2.0}]))
        assert caught.value.path == (0, "choice")


class TestMaterializeEnums:
    @pytest.mark.parametrize("value", [True, False])
    def test_booleans_do_not_materialize_as_numeric_members(self, value: bool) -> None:
        class Number(Enum):
            ZERO = 0
            ONE = 1

        schema = StandardSchemaAdapter().compile(Number)
        with pytest.raises(ValidationError):
            schema.validate(materialize_json(schema, value))

    @pytest.mark.parametrize("value", [0, 1, 0.0, 1.0])
    def test_numbers_do_not_materialize_as_boolean_members(self, value: int | float) -> None:
        class Flag(Enum):
            NO = False
            YES = True

        schema = StandardSchemaAdapter().compile(Flag)
        with pytest.raises(ValidationError):
            schema.validate(materialize_json(schema, value))

    @pytest.mark.parametrize("value", [1, 1.0])
    def test_equivalent_json_numbers_still_select_the_declared_member(
        self, value: int | float
    ) -> None:
        schema = StandardSchemaAdapter().compile(Priority)
        assert schema.validate(materialize_json(schema, value)) is Priority.LOW
        assert materialize_json(schema, Priority.LOW) is Priority.LOW

    def test_unknown_values_do_not_call_missing_hooks(self) -> None:
        calls: list[object] = []

        class Status(Enum):
            ACTIVE = "active"

            @classmethod
            def _missing_(cls, value: object) -> Status:
                calls.append(value)
                return cls.ACTIVE

        schema = StandardSchemaAdapter().compile(Status)
        with pytest.raises(ValidationError):
            schema.validate(materialize_json(schema, "unknown"))
        assert calls == []

    def test_invalid_enum_branch_falls_back_to_boolean_union_member(self) -> None:
        schema = StandardSchemaAdapter().compile(Priority | bool)
        assert schema.validate(materialize_json(schema, True)) is True

    def test_invalid_nested_enum_retains_its_path(self) -> None:
        schema = StandardSchemaAdapter().compile(list[dict[str, Priority]])
        with pytest.raises(ValidationError) as caught:
            schema.validate(materialize_json(schema, [{"priority": True}]))
        assert caught.value.path == (0, "priority")


class TestMaterializeNumbers:
    @pytest.mark.parametrize("value", [10**400, -(10**400)], ids=["positive", "negative"])
    def test_out_of_range_integer_is_a_validation_error(self, value: int) -> None:
        schema = StandardSchemaAdapter().compile(float)
        with pytest.raises(ValidationError, match="outside the float range"):
            materialize_json(schema, value)

    @pytest.mark.parametrize("value", [10**400, -(10**400)], ids=["positive", "negative"])
    def test_out_of_range_integer_preserves_nested_error_path(self, value: int) -> None:
        schema = StandardSchemaAdapter().compile(list[dict[str, float]])
        with pytest.raises(ValidationError) as caught:
            materialize_json(schema, [{"factor": value}])
        assert caught.value.path == (0, "factor")

    @pytest.mark.parametrize("value", [10**400, -(10**400)], ids=["positive", "negative"])
    def test_union_can_fall_back_to_an_integer_member(self, value: int) -> None:
        schema = StandardSchemaAdapter().compile(float | int)
        result = schema.validate(materialize_json(schema, value))
        assert type(result) is int
        assert result == value

    def test_a_json_integer_materializes_as_the_declared_float(self) -> None:
        schema = StandardSchemaAdapter().compile(float)
        assert materialize_json(schema, 3) == 3.0
        assert type(materialize_json(schema, 3)) is float
        assert schema.validate(materialize_json(schema, 3)) == 3.0

    def test_a_boolean_never_widens_to_a_float(self) -> None:
        schema = StandardSchemaAdapter().compile(float)
        assert materialize_json(schema, True) is True
        with pytest.raises(ValidationError, match="expected float, got bool"):
            schema.validate(materialize_json(schema, True))

    def test_an_integer_input_still_refuses_a_float(self) -> None:
        schema = StandardSchemaAdapter().compile(int)
        with pytest.raises(ValidationError, match="expected int, got float"):
            schema.validate(materialize_json(schema, 3.0))
