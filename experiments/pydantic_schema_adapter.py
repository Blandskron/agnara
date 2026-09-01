"""Experimental Pydantic implementation of Agnara's schema port.

This module is evidence for backlog items E2.6 and E2.7. It deliberately
lives outside `packages/`: importing it opts into pydantic, while every
production Agnara distribution retains its documented dependency boundary.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import pydantic
from pydantic import TypeAdapter

from agnara import SchemaError, ValidationError

__all__ = ["PydanticSchemaAdapter", "PydanticTypeSchema"]


class PydanticTypeSchema(NamedTuple):
    """Immutable compiled schema backed by Pydantic.

    Pydantic's TypeAdapter stores the compiled core schema and generates
    JSON Schema mappings on demand.
    """

    annotation: Any
    adapter: TypeAdapter[Any]

    def validate(self, value: object) -> Any:
        """Strictly validate builtin input and construct the declared type."""
        try:
            return self.adapter.validate_python(value, strict=True)
        except pydantic.ValidationError as error:
            raise _agnara_validation_error(error) from error

    def json_schema(self) -> dict[str, Any]:
        """Return a fresh plain-data copy of the compiled JSON Schema."""
        return self.adapter.json_schema()


class PydanticSchemaAdapter:
    """Compile Pydantic-compatible annotations into Agnara type schemas."""

    def compile(self, annotation: Any) -> PydanticTypeSchema:
        """Compile now, so unsupported annotations fail during startup."""
        try:
            adapter = TypeAdapter(annotation)
        except pydantic.errors.PydanticSchemaGenerationError as error:
            name = getattr(annotation, "__qualname__", repr(annotation))
            raise SchemaError(
                f"{name} is not supported by the Pydantic prototype: {error}"
            ) from error
        return PydanticTypeSchema(annotation, adapter)

    def supports(self, annotation: Any) -> bool:
        """Return whether `compile` accepts the annotation."""
        try:
            self.compile(annotation)
        except SchemaError:
            return False
        return True


def _agnara_validation_error(error: pydantic.ValidationError) -> ValidationError:
    """Translate Pydantic's structured errors into Agnara's protocol-neutral error.

    When multiple validation errors occur, this prototype reports the first one
    to keep the ValidationError shape simple.
    """
    errors = error.errors()
    if not errors:
        return ValidationError(str(error))

    first = errors[0]
    return ValidationError(first["msg"], path=tuple(first["loc"]))
