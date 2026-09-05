"""The introspection snapshot stays plain data, enforceably.

`ARCHITECTURE.md` section 10 requires the snapshot to be a safe projection
rather than a dump of runtime objects, and RFC 0003 repeats it. A prose rule
about what a descriptor "must not" hold is only as good as the next reviewer,
so these tests read the descriptor definitions and fail when a field type
would make a handler, provider, policy or schema object reachable.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from agnara import introspection
from agnara.introspection import descriptors

#: Everything a descriptor field is allowed to be. Nothing here can carry a
#: reference to a live object, so no traversal of a snapshot can reach one.
ALLOWED_FIELD_TYPES = {"str", "bool", "int", "float", "None"}

DESCRIPTOR_TYPES = tuple(
    value
    for value in vars(descriptors).values()
    if inspect.isclass(value)
    and dataclasses.is_dataclass(value)
    and value.__module__ == descriptors.__name__
)


def _minimal(descriptor: type) -> dict[str, object]:
    """Build one instance from required fields alone, using valid placeholders."""
    values: dict[str, object] = {}
    for field in dataclasses.fields(descriptor):  # type: ignore
        if field.default is not dataclasses.MISSING:
            continue
        annotation = field.type if isinstance(field.type, str) else str(field.type)
        if "bool" in annotation:
            values[field.name] = True
        elif "TypeReference" in annotation:
            values[field.name] = descriptors.TypeReference("Placeholder")
        elif field.name == "id":
            values[field.name] = "app.capability"
        elif field.name == "schema" or field.name == "detail":
            values[field.name] = "{}"
        else:
            values[field.name] = "placeholder"
    return values


def _leaf_types(annotation: str) -> set[str]:
    """Split a field annotation into the names it is built from."""
    cleaned = annotation.replace("tuple[", " ").replace("...", " ")
    for character in "[]|,":
        cleaned = cleaned.replace(character, " ")
    return {part for part in cleaned.split() if part}


def test_every_descriptor_is_a_frozen_slotted_dataclass() -> None:
    assert DESCRIPTOR_TYPES
    for descriptor in DESCRIPTOR_TYPES:
        assert descriptor.__dataclass_params__.frozen, descriptor.__name__
        # Slotted, so an instance cannot grow an attribute that carries state
        # the contract never declared.
        assert "__slots__" in vars(descriptor), descriptor.__name__
        assert not hasattr(descriptor(**_minimal(descriptor)), "__dict__"), descriptor.__name__


@pytest.mark.parametrize("descriptor", DESCRIPTOR_TYPES, ids=lambda value: value.__name__)
def test_no_descriptor_field_can_reference_a_runtime_object(descriptor: type) -> None:
    allowed = ALLOWED_FIELD_TYPES | {value.__name__ for value in DESCRIPTOR_TYPES}
    for field in dataclasses.fields(descriptor):  # type: ignore
        annotation = field.type if isinstance(field.type, str) else str(field.type)
        unexpected = _leaf_types(annotation) - allowed
        assert not unexpected, (
            f"{descriptor.__name__}.{field.name} may hold {sorted(unexpected)}, which can "
            "reference a runtime object; publish a name or JSON text instead"
        )


def test_the_snapshot_declares_its_own_format_and_version() -> None:
    assert introspection.INTROSPECTION_FORMAT == "agnara-introspection"
    # Versioned independently of the Agnara release and of OpenAPI. Changing
    # this is a contract decision, not a release side effect.
    assert introspection.INTROSPECTION_VERSION == "0"
    snapshot = introspection.IntrospectionSnapshot()
    assert snapshot.json_data()["format"] == introspection.INTROSPECTION_FORMAT
    assert snapshot.json_data()["version"] == introspection.INTROSPECTION_VERSION


def test_every_descriptor_type_is_part_of_the_published_contract() -> None:
    """A descriptor a consumer cannot name is one it cannot be given."""
    exported = set(introspection.__all__)
    assert {value.__name__ for value in DESCRIPTOR_TYPES} <= exported
    for name in exported:
        assert hasattr(introspection, name), name
