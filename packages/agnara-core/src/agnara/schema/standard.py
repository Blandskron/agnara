"""A standard-library schema adapter.

This is Agnara's reference implementation of the schema port: no third-party
dependency, no code generation, nothing clever. It exists so the port has a
working consumer, so a project can run without choosing a validation
library, and so faster adapters have something to be measured against.

Currently covers primitives only. Dataclasses and containers follow in
E2.2/E2.3.

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
"""

from __future__ import annotations

from types import NoneType
from typing import Any, Final

from agnara._frozen import frozen_slots_dataclass
from agnara.errors import SchemaError, ValidationError
from agnara.schema.port import JsonSchema, TypeSchema

__all__ = [
    "AnySchema",
    "NoneSchema",
    "PrimitiveSchema",
    "StandardSchemaAdapter",
]

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
class StandardSchemaAdapter:
    """Compiles primitive annotations using only the standard library."""

    def compile(self, annotation: Any) -> TypeSchema:
        if annotation is Any:
            return AnySchema()
        if annotation is None or annotation is NoneType:
            return NoneSchema()
        if isinstance(annotation, type) and annotation in _JSON_TYPES:
            return PrimitiveSchema(annotation)
        raise SchemaError(
            f"{self._render(annotation)} is not supported by "
            f"{type(self).__name__}; it currently handles "
            f"{self._supported()} only"
        )

    def supports(self, annotation: Any) -> bool:
        return (
            annotation is Any
            or annotation is None
            or annotation is NoneType
            or (isinstance(annotation, type) and annotation in _JSON_TYPES)
        )

    @staticmethod
    def _supported() -> str:
        names = [python_type.__name__ for python_type in _JSON_TYPES]
        return ", ".join([*names, "None", "Any"])

    @staticmethod
    def _render(annotation: Any) -> str:
        name = getattr(annotation, "__name__", None)
        return str(name) if name else repr(annotation)
