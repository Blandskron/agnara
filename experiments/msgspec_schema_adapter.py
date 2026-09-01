"""Experimental msgspec implementation of Agnara's schema port.

This module is evidence for backlog items E2.5 and E2.7. It deliberately
lives outside ``packages/``: importing it opts into msgspec, while every
production Agnara distribution retains its documented dependency boundary.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple, cast

import msgspec

from agnara import SchemaError, ValidationError

__all__ = ["MsgspecSchemaAdapter", "MsgspecTypeSchema"]


_ERROR_LOCATION = re.compile(r"^(?P<message>.*) - at `(?P<path>\$.*)`$")
_PATH_SEGMENT = re.compile(r"\.([^.[\]]+)|\[(\d+)\]")


class MsgspecTypeSchema(NamedTuple):
    """Immutable compiled schema backed by msgspec 0.21.

    The generated JSON Schema is encoded once at compilation. Keeping bytes
    instead of a mutable dict means callers cannot mutate shared registry
    state through ``json_schema()``.
    """

    annotation: Any
    encoded_json_schema: bytes

    def validate(self, value: object) -> Any:
        """Strictly validate builtin input and construct the declared type."""
        try:
            return msgspec.convert(value, self.annotation, strict=True)
        except msgspec.ValidationError as error:
            raise _agnara_validation_error(error) from error

    def json_schema(self) -> dict[str, Any]:
        """Return a fresh plain-data copy of the compiled JSON Schema."""
        return cast(dict[str, Any], msgspec.json.decode(self.encoded_json_schema))


class MsgspecSchemaAdapter:
    """Compile msgspec-compatible annotations into Agnara type schemas."""

    def compile(self, annotation: Any) -> MsgspecTypeSchema:
        """Compile now, so unsupported annotations fail during startup."""
        try:
            schema = msgspec.json.schema(annotation)
            encoded_schema = msgspec.json.encode(schema)
        except (TypeError, ValueError) as error:
            name = getattr(annotation, "__qualname__", repr(annotation))
            raise SchemaError(
                f"{name} is not supported by the msgspec prototype: {error}"
            ) from error
        return MsgspecTypeSchema(annotation, encoded_schema)

    def supports(self, annotation: Any) -> bool:
        """Return whether ``compile`` accepts the annotation."""
        try:
            self.compile(annotation)
        except SchemaError:
            return False
        return True


def _agnara_validation_error(error: msgspec.ValidationError) -> ValidationError:
    """Translate msgspec's human-readable JSONPath when it is unambiguous.

    msgspec 0.21 exposes no structured path attribute. Object fields and
    sequence indices can still be recovered losslessly from its documented
    error rendering. Dictionary keys render as ``[...]``; those errors retain
    the provider location in the message instead of inventing an Agnara path.
    """
    rendered = str(error)
    match = _ERROR_LOCATION.fullmatch(rendered)
    if match is None:
        return ValidationError(rendered)

    path_text = match.group("path")
    path: list[str | int] = []
    position = 1  # Skip the JSONPath root marker, ``$``.
    while position < len(path_text):
        segment = _PATH_SEGMENT.match(path_text, position)
        if segment is None:
            return ValidationError(rendered)
        field, index = segment.groups()
        path.append(field if field is not None else int(cast(str, index)))
        position = segment.end()
    return ValidationError(match.group("message"), path=tuple(path))
