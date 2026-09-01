"""The schema port: what Agnara needs from a type system, and no more.

ADR 0004 keeps Pydantic and msgspec out of the core. What the core owns is
the *contract*: given a Python annotation, produce something that can check
a value against it and describe it as JSON Schema. Anything that satisfies
these two protocols is a schema implementation, with no Agnara base class to
inherit and no registration step.

Both are `Protocol`s rather than abstract bases so an adapter can satisfy
them structurally — a msgspec or Pydantic bridge should not have to import
Agnara to be usable by it.

The split is deliberate:

``SchemaAdapter``
    Compiles an annotation into a `TypeSchema`. Runs at startup.

``TypeSchema``
    The compiled result. Runs per invocation, so it does no introspection
    (ADR 0005, PRINCIPLES.md P5).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "JsonSchema",
    "SchemaAdapter",
    "TypeSchema",
]

#: A JSON Schema document fragment, as plain data.
#:
#: Deliberately a bare mapping. The core does not name a dialect and does
#: not emit ``$schema``: which dialect applies is a property of the document
#: an adapter assembles, not of one field's schema, and pinning it here
#: would put a protocol concern in the kernel (PRINCIPLES.md P3).
type JsonSchema = Mapping[str, Any]


@runtime_checkable
class TypeSchema(Protocol):
    """A compiled schema for one Python annotation.

    Implementations must be immutable and safe to share across threads once
    built, because the compiled registry is frozen and read without locking
    after startup (PRINCIPLES.md P6).
    """

    def validate(self, value: object) -> Any:
        """Check ``value`` and return what the handler should receive.

        Returning rather than returning ``None`` lets an implementation
        coerce — an HTTP query string is text, and something has to turn it
        into the `int` the handler declared. Whether a given adapter coerces
        or insists on exact types is the adapter's documented choice; the
        port only requires that the returned value satisfies the annotation.

        Raises `ValidationError` when the value cannot satisfy the schema.
        """
        ...

    def json_schema(self) -> JsonSchema:
        """Describe this schema as JSON Schema.

        Used for OpenAPI, MCP tool descriptions and Agnara's own manifest.
        Returns plain data so no consumer inherits a framework type.
        """
        ...


@runtime_checkable
class SchemaAdapter(Protocol):
    """Compiles Python annotations into `TypeSchema` objects.

    Called during startup compilation. An annotation it cannot support must
    fail here, loudly, rather than at the first invocation that happens to
    exercise it (ADR 0005).
    """

    def compile(self, annotation: Any) -> TypeSchema:
        """Compile ``annotation`` into a reusable schema.

        Raises `SchemaError` if the annotation is not supported.
        """
        ...

    def supports(self, annotation: Any) -> bool:
        """Whether `compile` would succeed for ``annotation``.

        Lets a caller choose between adapters, or report every unsupported
        annotation in a project at once instead of failing on the first.
        """
        ...
