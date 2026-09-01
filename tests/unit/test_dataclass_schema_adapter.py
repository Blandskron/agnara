"""E2.3 — strict standard-library dataclass schemas."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, InitVar, dataclass, field, make_dataclass
from typing import ClassVar

import pytest

from agnara import SchemaError, StandardSchemaAdapter, TypeSchema, ValidationError
from agnara.schema import DataclassFieldSchema, DataclassSchema


@dataclass
class Address:
    city: str
    postcode: int | None = None


@dataclass
class Customer:
    name: str
    address: Address
    tags: list[str] = field(default_factory=list)


@dataclass
class Entity:
    identifier: int


@dataclass
class ActiveEntity(Entity):
    active: bool = True


@dataclass
class WithClassVariable:
    kind: ClassVar[str] = "value"
    value: int = 0


def factory_must_not_run() -> list[str]:
    raise AssertionError("default_factory ran during schema compilation")


@dataclass
class WithFactory:
    name: str
    items: list[str] = field(default_factory=factory_must_not_run)


@dataclass
class RecursiveNode:
    child: RecursiveNode | None = None


BrokenReference = make_dataclass("BrokenReference", [("value", "MissingType")])


@dataclass
class WithComputedField:
    value: int
    computed: int = field(init=False, default=0)


@dataclass
class WithInitVariable:
    secret: InitVar[str]
    value: int


class OrdinaryClass:
    pass


@pytest.fixture
def adapter() -> StandardSchemaAdapter:
    return StandardSchemaAdapter()


class TestDataclassCompilation:
    def test_compiles_a_dataclass_class(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(Address)
        assert isinstance(schema, DataclassSchema)
        assert isinstance(schema, TypeSchema)

    def test_compiles_each_field_recursively(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(Customer)
        assert isinstance(schema, DataclassSchema)
        assert [field_schema.name for field_schema in schema.fields] == [
            "name",
            "address",
            "tags",
        ]
        assert all(isinstance(field_schema, DataclassFieldSchema) for field_schema in schema.fields)

    def test_resolves_postponed_annotations(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(Customer)
        value = Customer("Ada", Address("Santiago", 8320000), ["active"])
        assert schema.validate(value) is value

    def test_compiles_inherited_fields_in_order(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(ActiveEntity)
        assert isinstance(schema, DataclassSchema)
        assert [field_schema.name for field_schema in schema.fields] == [
            "identifier",
            "active",
        ]

    def test_ignores_class_variables(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(WithClassVariable)
        assert isinstance(schema, DataclassSchema)
        assert [field_schema.name for field_schema in schema.fields] == ["value"]


class TestDataclassValidation:
    def test_accepts_and_returns_the_exact_instance(self, adapter: StandardSchemaAdapter) -> None:
        value = Address("Santiago", 8320000)
        assert adapter.compile(Address).validate(value) is value

    @pytest.mark.parametrize(
        "value",
        [
            {"city": "Santiago", "postcode": 8320000},
            object(),
        ],
    )
    def test_rejects_non_instances(self, adapter: StandardSchemaAdapter, value: object) -> None:
        with pytest.raises(ValidationError, match="expected Address"):
            adapter.compile(Address).validate(value)

    def test_rejects_a_subclass_instance(self, adapter: StandardSchemaAdapter) -> None:
        @dataclass
        class DetailedAddress(Address):
            country: str = "CL"

        with pytest.raises(ValidationError, match="got DetailedAddress"):
            adapter.compile(Address).validate(DetailedAddress("Santiago"))

    def test_reports_the_invalid_field_name(self, adapter: StandardSchemaAdapter) -> None:
        value = Address("Santiago", "invalid")  # ty: ignore[invalid-argument-type]
        with pytest.raises(ValidationError) as caught:
            adapter.compile(Address).validate(value)
        assert caught.value.path == ("postcode",)

    def test_accumulates_nested_dataclass_paths(self, adapter: StandardSchemaAdapter) -> None:
        value = Customer(
            "Ada",
            Address("Santiago", "invalid"),  # ty: ignore[invalid-argument-type]
        )
        with pytest.raises(ValidationError) as caught:
            adapter.compile(Customer).validate(value)
        assert caught.value.path == ("address", "postcode")
        assert caught.value.location == "address.postcode"

    def test_accumulates_dataclass_and_container_paths(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        value = Customer(
            "Ada",
            Address("Santiago"),
            ["ok", 2],  # ty: ignore[invalid-argument-type]
        )
        with pytest.raises(ValidationError) as caught:
            adapter.compile(Customer).validate(value)
        assert caught.value.path == ("tags", 1)

    def test_reports_a_deleted_required_field(self, adapter: StandardSchemaAdapter) -> None:
        value = Address("Santiago")
        del value.city
        with pytest.raises(ValidationError, match="field is missing") as caught:
            adapter.compile(Address).validate(value)
        assert caught.value.path == ("city",)


class TestDataclassJsonSchema:
    def test_projects_properties_required_and_closed_shape(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        assert adapter.compile(Address).json_schema() == {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "postcode": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            },
            "additionalProperties": False,
            "required": ["city"],
        }

    def test_defaults_and_factories_make_fields_non_required_without_running_factory(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        schema = adapter.compile(WithFactory).json_schema()
        assert schema["required"] == ["name"]

    def test_omits_required_when_every_field_has_a_default(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        schema = adapter.compile(WithClassVariable).json_schema()
        assert "required" not in schema

    def test_projects_nested_dataclasses_inline(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(Customer).json_schema()
        assert schema["properties"]["address"] == adapter.compile(Address).json_schema()

    def test_returns_fresh_nested_plain_data(self, adapter: StandardSchemaAdapter) -> None:
        compiled = adapter.compile(Customer)
        first = dict(compiled.json_schema())
        first["properties"] = {}
        assert "address" in compiled.json_schema()["properties"]

    def test_returns_only_plain_mapping_and_sequence_types(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        schema = adapter.compile(Customer).json_schema()
        assert type(schema) is dict
        assert type(schema["properties"]) is dict
        assert type(schema["required"]) is list

    def test_declares_no_document_dialect(self, adapter: StandardSchemaAdapter) -> None:
        assert "$schema" not in adapter.compile(Customer).json_schema()


class TestUnsupportedDataclasses:
    def test_rejects_a_recursive_graph_at_compile_time(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        with pytest.raises(SchemaError, match="RecursiveNode -> RecursiveNode"):
            adapter.compile(RecursiveNode)

    def test_rejects_an_unresolved_annotation_actionably(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        with pytest.raises(SchemaError, match="could not be resolved") as caught:
            adapter.compile(BrokenReference)
        assert "MissingType" in str(caught.value)

    def test_rejects_init_false_until_schemas_are_directional(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        with pytest.raises(SchemaError, match="init=False"):
            adapter.compile(WithComputedField)

    def test_rejects_init_var_until_schemas_are_directional(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        with pytest.raises(SchemaError, match="InitVar"):
            adapter.compile(WithInitVariable)

    def test_rejects_a_dataclass_instance_as_an_annotation(
        self, adapter: StandardSchemaAdapter
    ) -> None:
        with pytest.raises(SchemaError):
            adapter.compile(Address("Santiago"))

    def test_rejects_an_ordinary_class(self, adapter: StandardSchemaAdapter) -> None:
        with pytest.raises(SchemaError):
            adapter.compile(OrdinaryClass)


class TestDataclassSupportsAndImmutability:
    @pytest.mark.parametrize("annotation", [Address, Customer, ActiveEntity, WithFactory])
    def test_supports_compilable_dataclasses(
        self, adapter: StandardSchemaAdapter, annotation: type
    ) -> None:
        assert adapter.supports(annotation)

    @pytest.mark.parametrize(
        "annotation",
        [RecursiveNode, BrokenReference, WithComputedField, WithInitVariable],
    )
    def test_does_not_support_rejected_dataclasses(
        self, adapter: StandardSchemaAdapter, annotation: type
    ) -> None:
        assert not adapter.supports(annotation)

    @pytest.mark.parametrize("annotation", [Address("Santiago"), OrdinaryClass])
    def test_supports_agrees_for_non_annotations(
        self, adapter: StandardSchemaAdapter, annotation: object
    ) -> None:
        assert not adapter.supports(annotation)

    def test_compiled_dataclass_schema_is_frozen(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(Address)
        with pytest.raises(FrozenInstanceError):
            schema.changed = True  # ty: ignore[unresolved-attribute]

    def test_compiled_field_descriptor_is_frozen(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(Address)
        assert isinstance(schema, DataclassSchema)
        with pytest.raises(FrozenInstanceError):
            schema.fields[0].name = "changed"  # ty: ignore[invalid-assignment]

    def test_compiled_dataclass_values_are_slotted(self, adapter: StandardSchemaAdapter) -> None:
        schema = adapter.compile(Address)
        assert isinstance(schema, DataclassSchema)
        assert not hasattr(schema, "__dict__")
        assert not hasattr(schema.fields[0], "__dict__")
