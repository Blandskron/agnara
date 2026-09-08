"""A standard-library schema adapter.

This is Agnara's reference implementation of the schema port: no third-party
dependency, no code generation, nothing clever. It exists so the port has a
working consumer, so a project can run without choosing a validation
library, and so faster adapters have something to be measured against.

It covers primitives, common standard-library type compositions and ordinary
dataclass object schemas.

## Strictness

This adapter does **not** coerce. ``validate("3")`` against `int` fails
rather than returning `3`.

The port permits coercion because a transport may need it — an HTTP query
string is text, and something has to turn it into the `int` a handler
declared. But that decision belongs to the transport, which knows its own
wire format. A capability invoked directly from Python, from a task or from
another capability has no wire format, and silently accepting `"3"` there
would hide a real bug. So the core adapter is strict and HTTP will convert
before it validates, rather than the core guessing on everyone's behalf.

## bool is not int

Python says `isinstance(True, int)` is true. A schema should not: a handler
declaring `int` and receiving `True` has almost certainly been passed the
wrong thing. `bool` is checked exactly, and rejected where `int` is wanted.

## Dataclasses

A dataclass annotation validates an exact instance and returns it unchanged.
Mapping-to-instance construction belongs at a boundary that knows its wire
format; the core adapter does not silently construct domain objects.

Field defaults make properties non-required in the JSON Schema projection,
but default factories are never executed during compilation. Recursive
dataclass graphs, `InitVar` and `init=False` fields fail at compile time until
the port has explicit reference and directional input/output semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import MISSING, InitVar, is_dataclass
from dataclasses import fields as dataclass_fields
from enum import Enum
from math import isfinite
from types import GenericAlias, NoneType, UnionType
from typing import Any, Final, Literal, Union, cast, get_args, get_origin, get_type_hints

from agnara._frozen import frozen_slots_dataclass
from agnara.errors import SchemaError, ValidationError
from agnara.schema.port import JsonSchema, TypeSchema

__all__ = [
    "AnySchema",
    "DataclassFieldSchema",
    "DataclassSchema",
    "DictionarySchema",
    "EnumSchema",
    "ListSchema",
    "LiteralSchema",
    "NoneSchema",
    "PrimitiveSchema",
    "StandardSchemaAdapter",
    "TupleSchema",
    "UnionSchema",
    "materialize_json",
    "serialize_json",
]

#: Deepest value `serialize_json` will walk. A handler that returns something
#: nested further has almost certainly returned a structure by mistake, and a
#: bound keeps a JSON transport from recursing without limit on its behalf. It
#: is no smaller than the deepest input a JSON transport admits, so a
#: capability that echoes an accepted value can always answer.
_MAX_OUTPUT_DEPTH: Final = 128

#: Python primitive -> its JSON Schema type keyword.
#:
#: `bytes` has no JSON representation; it is accepted for direct and
#: non-JSON transports and described as a string with a binary format, the
#: convention OpenAPI uses.
_JSON_TYPES: Final[dict[type, str]] = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
    bytes: "string",
}

_JSON_LITERAL_TYPES: Final[dict[type, str]] = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
    NoneType: "null",
}


@frozen_slots_dataclass
class PrimitiveSchema:
    """An exact-type check against one Python primitive."""

    python_type: type

    def validate(self, value: object) -> Any:
        # `type(...) is` rather than isinstance: a bool must not satisfy
        # int, and a subclass of str is not the declared type either.
        if type(value) is not self.python_type:
            raise ValidationError(
                f"expected {self.python_type.__name__}, got {type(value).__name__}"
            )
        return value

    def json_schema(self) -> JsonSchema:
        schema: dict[str, Any] = {"type": _JSON_TYPES[self.python_type]}
        if self.python_type is bytes:
            schema["format"] = "binary"
        return schema


@frozen_slots_dataclass
class NoneSchema:
    """Accepts only `None`, for a handler annotated `-> None`."""

    def validate(self, value: object) -> Any:
        if value is not None:
            raise ValidationError(f"expected None, got {type(value).__name__}")
        return None

    def json_schema(self) -> JsonSchema:
        return {"type": "null"}


@frozen_slots_dataclass
class AnySchema:
    """Accepts anything.

    `Any` is a real answer, not a missing one: it says the capability author
    deliberately declined to constrain this value. Rejecting it would push
    people toward omitting the annotation entirely, which says less.
    """

    def validate(self, value: object) -> Any:
        return value

    def json_schema(self) -> JsonSchema:
        # An empty schema is JSON Schema's "anything", and is not the same
        # as `true`; a mapping keeps the return type uniform.
        return {}


@frozen_slots_dataclass
class DataclassFieldSchema:
    """One recursively compiled instance field of a dataclass schema."""

    name: str
    schema: TypeSchema
    required: bool


@frozen_slots_dataclass
class DataclassSchema:
    """A strict schema for one standard-library dataclass type."""

    dataclass_type: type
    fields: tuple[DataclassFieldSchema, ...]

    def validate(self, value: object) -> Any:
        if type(value) is not self.dataclass_type:
            raise ValidationError(
                f"expected {self.dataclass_type.__name__}, got {type(value).__name__}"
            )
        for field_schema in self.fields:
            try:
                field_value = getattr(value, field_schema.name)
            except AttributeError as error:
                raise ValidationError("field is missing", path=(field_schema.name,)) from error
            try:
                field_schema.schema.validate(field_value)
            except ValidationError as error:
                raise error.at(field_schema.name) from error
        return value

    def json_schema(self) -> JsonSchema:
        properties = {
            field_schema.name: dict(field_schema.schema.json_schema())
            for field_schema in self.fields
        }
        required = [field_schema.name for field_schema in self.fields if field_schema.required]
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            schema["required"] = required
        return schema


@frozen_slots_dataclass
class ListSchema:
    """A homogeneous, exactly typed Python list."""

    item_schema: TypeSchema

    def validate(self, value: object) -> Any:
        if type(value) is not list:
            raise ValidationError(f"expected list, got {type(value).__name__}")
        for index, item in enumerate(value):
            try:
                self.item_schema.validate(item)
            except ValidationError as error:
                raise error.at(index) from error
        return value

    def json_schema(self) -> JsonSchema:
        return {"type": "array", "items": dict(self.item_schema.json_schema())}


@frozen_slots_dataclass
class DictionarySchema:
    """A Python dictionary with string keys and homogeneous values."""

    value_schema: TypeSchema

    def validate(self, value: object) -> Any:
        if type(value) is not dict:
            raise ValidationError(f"expected dict, got {type(value).__name__}")
        for key, item in value.items():
            if type(key) is not str:
                raise ValidationError(
                    f"expected str key, got {type(key).__name__}", path=("<key>",)
                )
            try:
                self.value_schema.validate(item)
            except ValidationError as error:
                raise error.at(key) from error
        return value

    def json_schema(self) -> JsonSchema:
        return {
            "type": "object",
            "additionalProperties": dict(self.value_schema.json_schema()),
        }


@frozen_slots_dataclass
class TupleSchema:
    """A fixed-length or homogeneous variadic Python tuple."""

    item_schemas: tuple[TypeSchema, ...]
    variadic: bool = False

    def validate(self, value: object) -> Any:
        if type(value) is not tuple:
            raise ValidationError(f"expected tuple, got {type(value).__name__}")
        if self.variadic:
            item_schema = self.item_schemas[0]
            schemas = (item_schema for _ in value)
        else:
            if len(value) != len(self.item_schemas):
                raise ValidationError(
                    f"expected tuple of length {len(self.item_schemas)}, got length {len(value)}"
                )
            schemas = iter(self.item_schemas)
        for index, (item, item_schema) in enumerate(zip(value, schemas, strict=True)):
            try:
                item_schema.validate(item)
            except ValidationError as error:
                raise error.at(index) from error
        return value

    def json_schema(self) -> JsonSchema:
        if self.variadic:
            return {
                "type": "array",
                "items": dict(self.item_schemas[0].json_schema()),
            }
        length = len(self.item_schemas)
        return {
            "type": "array",
            "prefixItems": [dict(schema.json_schema()) for schema in self.item_schemas],
            "items": False,
            "minItems": length,
            "maxItems": length,
        }


@frozen_slots_dataclass
class UnionSchema:
    """A value accepted by at least one compiled union member."""

    choices: tuple[TypeSchema, ...]

    def validate(self, value: object) -> Any:
        failures: list[ValidationError] = []
        for choice in self.choices:
            try:
                return choice.validate(value)
            except ValidationError as error:
                failures.append(error)
        most_specific = max(failures, key=lambda error: len(error.path))
        detail = "; ".join(error.message for error in failures)
        raise ValidationError(
            f"value does not match any union member ({detail})",
            path=most_specific.path,
        )

    def json_schema(self) -> JsonSchema:
        return {"anyOf": [dict(choice.json_schema()) for choice in self.choices]}


@frozen_slots_dataclass
class LiteralSchema:
    """A finite choice of exact JSON-compatible Python scalar values."""

    values: tuple[object, ...]

    def validate(self, value: object) -> Any:
        if not any(
            type(value) is type(candidate) and value == candidate for candidate in self.values
        ):
            raise ValidationError(f"expected one of {self.values!r}, got {value!r}")
        return value

    def json_schema(self) -> JsonSchema:
        if len(self.values) == 1:
            return {"const": self.values[0]}
        return {"enum": list(self.values)}


@frozen_slots_dataclass
class EnumSchema:
    """An exact standard-library enum type with JSON-compatible values."""

    enum_type: type[Enum]
    values: tuple[object, ...]

    def validate(self, value: object) -> Any:
        if type(value) is not self.enum_type:
            raise ValidationError(f"expected {self.enum_type.__name__}, got {type(value).__name__}")
        return value

    def json_schema(self) -> JsonSchema:
        schema: dict[str, Any] = {"enum": list(self.values)}
        value_types = {type(value) for value in self.values}
        if len(value_types) == 1:
            schema["type"] = _JSON_LITERAL_TYPES[value_types.pop()]
        return schema


@frozen_slots_dataclass
class StandardSchemaAdapter:
    """Compiles common Python annotations using only the standard library."""

    def compile(self, annotation: Any) -> TypeSchema:
        return self._compile(annotation, dataclass_stack=())

    def _compile(self, annotation: Any, dataclass_stack: tuple[type, ...]) -> TypeSchema:
        if annotation is Any:
            return AnySchema()
        if annotation is None or annotation is NoneType:
            return NoneSchema()
        if isinstance(annotation, type) and annotation in _JSON_TYPES:
            return PrimitiveSchema(annotation)
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return self._compile_enum(annotation)
        if isinstance(annotation, type) and is_dataclass(annotation):
            return self._compile_dataclass(annotation, dataclass_stack)

        origin = get_origin(annotation)
        arguments = get_args(annotation)
        if origin is list:
            if len(arguments) != 1:
                raise self._malformed(annotation, "exactly one item type is required")
            return ListSchema(self._compile(arguments[0], dataclass_stack))
        if origin is dict:
            if len(arguments) != 2:
                raise self._malformed(annotation, "key and value types are required")
            key_type, value_type = arguments
            if key_type is not str:
                raise self._malformed(annotation, "dictionary keys must be str")
            return DictionarySchema(self._compile(value_type, dataclass_stack))
        if origin is tuple:
            if not arguments and not isinstance(annotation, GenericAlias):
                raise self._malformed(annotation, "at least one item type is required")
            if len(arguments) == 2 and arguments[1] is Ellipsis:
                return TupleSchema((self._compile(arguments[0], dataclass_stack),), variadic=True)
            return TupleSchema(
                tuple(self._compile(argument, dataclass_stack) for argument in arguments)
            )
        if origin is Literal:
            return self._compile_literal(annotation, arguments)
        if origin is Union or origin is UnionType:
            return UnionSchema(
                tuple(self._compile(argument, dataclass_stack) for argument in arguments)
            )
        raise SchemaError(
            f"{self._render(annotation)} is not supported by "
            f"{type(self).__name__}; it currently handles "
            f"{self._supported()} only"
        )

    def supports(self, annotation: Any) -> bool:
        try:
            self.compile(annotation)
        except SchemaError:
            return False
        return True

    def _compile_dataclass(
        self, annotation: type, dataclass_stack: tuple[type, ...]
    ) -> DataclassSchema:
        if annotation in dataclass_stack:
            cycle = " -> ".join(
                dataclass_type.__name__ for dataclass_type in (*dataclass_stack, annotation)
            )
            raise self._malformed(annotation, f"recursive dataclass graph: {cycle}")

        try:
            type_hints = get_type_hints(annotation)
        except Exception as error:
            raise self._malformed(
                annotation, f"field annotations could not be resolved: {error}"
            ) from error

        init_vars = [
            name for name, field_type in type_hints.items() if isinstance(field_type, InitVar)
        ]
        if init_vars:
            joined = ", ".join(init_vars)
            raise self._malformed(
                annotation,
                f"InitVar fields require directional schema support: {joined}",
            )

        compiled_fields: list[DataclassFieldSchema] = []
        next_stack = (*dataclass_stack, annotation)
        for field in dataclass_fields(cast(Any, annotation)):
            if not field.init:
                raise self._malformed(
                    annotation,
                    f"field {field.name!r} uses init=False, which requires "
                    "directional schema support",
                )
            field_type = type_hints.get(field.name)
            if field_type is None:
                raise self._malformed(
                    annotation, f"field {field.name!r} has no resolvable annotation"
                )
            compiled_fields.append(
                DataclassFieldSchema(
                    name=field.name,
                    schema=self._compile(field_type, next_stack),
                    required=field.default is MISSING and field.default_factory is MISSING,
                )
            )
        return DataclassSchema(annotation, tuple(compiled_fields))

    def _compile_literal(self, annotation: Any, arguments: tuple[object, ...]) -> LiteralSchema:
        if not arguments:
            raise self._malformed(annotation, "at least one value is required")
        for value in arguments:
            # The typing specification permits int, bool, str, bytes, enum
            # members and None in Literal. Bytes and enum members are not
            # JSON scalar values themselves; floats are JSON values but are
            # not valid Literal parameters.
            if type(value) not in {bool, int, str, NoneType}:
                raise self._malformed(
                    annotation,
                    "literal values must be JSON-compatible values allowed by typing.Literal",
                )
        return LiteralSchema(arguments)

    def _compile_enum(self, annotation: type[Enum]) -> EnumSchema:
        values = tuple(member.value for member in annotation)
        if not values:
            raise self._malformed(annotation, "an enum must define at least one member")
        if not all(self._is_json_scalar(value) for value in values):
            raise self._malformed(annotation, "enum values must be finite JSON scalar values")
        return EnumSchema(annotation, values)

    @staticmethod
    def _is_json_scalar(value: object) -> bool:
        if type(value) not in _JSON_LITERAL_TYPES:
            return False
        return type(value) is not float or isfinite(value)

    def _malformed(self, annotation: Any, reason: str) -> SchemaError:
        return SchemaError(f"{self._render(annotation)} is not supported: {reason}")

    @staticmethod
    def _supported() -> str:
        names = [python_type.__name__ for python_type in _JSON_TYPES]
        return ", ".join(
            [
                *names,
                "None",
                "Any",
                "list[T]",
                "dict[str, T]",
                "tuple[...]",
                "unions",
                "Literal",
                "Enum",
                "dataclasses",
            ]
        )

    @staticmethod
    def _render(annotation: Any) -> str:
        name = getattr(annotation, "__name__", None)
        return str(name) if name else repr(annotation)


def materialize_json(schema: TypeSchema, value: object) -> Any:
    """Materialize standard-library Python values from decoded JSON data.

    This is an explicit wire-boundary operation. The standard validator stays
    strict for direct Python invocation, while JSON transports can request the
    conversions JSON cannot represent: dataclass instances, tuples and enum
    members. Unknown schema implementations receive the value unchanged.
    """
    if isinstance(schema, DataclassSchema) and type(value) is dict:
        object_value = cast(dict[str, Any], value)
        fields = {field.name: field for field in schema.fields}
        unexpected = sorted(set(object_value).difference(fields))
        if unexpected:
            raise ValidationError("unexpected field", path=(unexpected[0],))
        missing = sorted(
            field.name
            for field in schema.fields
            if field.required and field.name not in object_value
        )
        if missing:
            raise ValidationError("field is missing", path=(missing[0],))
        arguments: dict[str, Any] = {}
        for name, item in object_value.items():
            try:
                arguments[name] = materialize_json(fields[name].schema, item)
            except ValidationError as error:
                raise error.at(name) from error
        try:
            return schema.dataclass_type(**arguments)
        except (TypeError, ValueError) as error:
            raise ValidationError("could not construct the declared dataclass") from error

    if isinstance(schema, ListSchema) and type(value) is list:
        materialized: list[Any] = []
        for index, item in enumerate(cast(list[Any], value)):
            try:
                materialized.append(materialize_json(schema.item_schema, item))
            except ValidationError as error:
                raise error.at(index) from error
        return materialized

    if isinstance(schema, DictionarySchema) and type(value) is dict:
        materialized_mapping: dict[str, Any] = {}
        for name, item in cast(dict[str, Any], value).items():
            try:
                materialized_mapping[name] = materialize_json(schema.value_schema, item)
            except ValidationError as error:
                raise error.at(name) from error
        return materialized_mapping

    if isinstance(schema, TupleSchema) and type(value) is list:
        sequence = cast(list[Any], value)
        if not schema.variadic and len(sequence) != len(schema.item_schemas):
            return tuple(sequence)
        item_schemas = (
            (schema.item_schemas[0] for _ in sequence)
            if schema.variadic
            else iter(schema.item_schemas)
        )
        materialized_tuple: list[Any] = []
        for index, (item, item_schema) in enumerate(zip(sequence, item_schemas, strict=True)):
            try:
                materialized_tuple.append(materialize_json(item_schema, item))
            except ValidationError as error:
                raise error.at(index) from error
        return tuple(materialized_tuple)

    if isinstance(schema, EnumSchema):
        try:
            return schema.enum_type(value)
        except TypeError, ValueError:
            return value

    if isinstance(schema, PrimitiveSchema) and schema.python_type is float and type(value) is int:
        # JSON has one number type. A wire value ``3`` satisfies the published
        # ``{"type": "number"}`` schema, so a JSON transport owes the handler
        # the float it declared; ``bool`` is excluded by the exact type check.
        return float(value)

    if isinstance(schema, UnionSchema):
        for choice in schema.choices:
            try:
                candidate = materialize_json(choice, value)
                choice.validate(candidate)
            except ValidationError:
                continue
            return candidate

    return value


def serialize_json(value: object) -> Any:
    """Project a handler's return value onto plain JSON data.

    The output counterpart of `materialize_json`, and the one definition every
    JSON transport shares so a capability cannot succeed over one protocol and
    fail over another for returning the same value. Enum members become their
    values, dataclass instances become objects, any mapping becomes an object
    with string keys and any list or tuple becomes an array. Finite floats,
    ``bool``, ``int``, ``str`` and ``None`` pass through.

    Raises `ValidationError`, located at the offending value, for a cycle, a
    non-finite float, a non-string object key, an unsupported type or a
    structure deeper than 128 levels. What a transport does with that failure
    is its own decision; none of them should describe the value to a caller.
    """
    return _serialize_json(value, set(), 0)


def _serialize_json(value: object, active: set[int], depth: int) -> Any:
    if isinstance(value, Enum):
        # Before the scalar checks: a StrEnum or IntEnum member is also a str
        # or int, and the transport should receive the plain value, not the
        # member.
        return _serialize_json(value.value, active, depth)
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValidationError("non-finite float is not JSON")
        return value
    if depth >= _MAX_OUTPUT_DEPTH:
        raise ValidationError(f"output nests deeper than {_MAX_OUTPUT_DEPTH} levels")

    is_object = is_dataclass(value) and not isinstance(value, type)
    if not (is_object or isinstance(value, Mapping | list | tuple)):
        raise ValidationError(f"unsupported output type {type(value).__name__}")
    identity = id(value)
    if identity in active:
        raise ValidationError("cyclic output value")
    active.add(identity)
    try:
        if isinstance(value, Mapping):
            plain: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValidationError("JSON object keys must be strings")
                plain[key] = _located(item, active, depth, key)
            return plain
        if isinstance(value, list | tuple):
            return [_located(item, active, depth, index) for index, item in enumerate(value)]
        return {
            field.name: _located(getattr(value, field.name), active, depth, field.name)
            for field in dataclass_fields(value)
        }
    finally:
        active.remove(identity)


def _located(value: object, active: set[int], depth: int, segment: str | int) -> Any:
    try:
        return _serialize_json(value, active, depth + 1)
    except ValidationError as error:
        raise error.at(segment) from None
