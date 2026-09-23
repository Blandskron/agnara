"""Optional-library schema boundary evidence; no adapter ships from Agnara."""

from __future__ import annotations

from dataclasses import dataclass

import msgspec
import pytest
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from agnara import SchemaError, StandardSchemaAdapter, ValidationError
from agnara.schema import materialize_json, serialize_json


@dataclass(frozen=True)
class Address:
    city: str


@dataclass(frozen=True)
class Payload:
    name: str
    address: Address | None
    tags: list[str]


class PydanticPayload(BaseModel):
    name: str
    address: dict[str, str] | None
    tags: list[str]


class MagspecPayload(msgspec.Struct):
    name: str
    address: dict[str, str] | None
    tags: list[str]


def _standard(value: object) -> Payload:
    schema = StandardSchemaAdapter().compile(Payload)
    return materialize_json(schema, value)


@pytest.mark.parametrize(
    "value",
    [
        {"name": "Ada", "address": {"city": "Santiago"}, "tags": ["one", "two"]},
        {"name": "Ada", "address": None, "tags": []},
    ],
)
def test_optional_models_normalize_to_the_standard_library_runtime_boundary(
    value: dict[str, object],
) -> None:
    pydantic_value = PydanticPayload.model_validate(value).model_dump(mode="json")
    msgspec_value = msgspec.to_builtins(msgspec.convert(value, type=MagspecPayload))
    assert _standard(pydantic_value) == _standard(msgspec_value)
    assert serialize_json(_standard(pydantic_value)) == value


@pytest.mark.parametrize("value", [{"name": "Ada", "tags": [1]}])
def test_external_and_standard_validation_reject_invalid_nested_values(
    value: dict[str, object],
) -> None:
    with pytest.raises(PydanticValidationError):
        PydanticPayload.model_validate(value)
    with pytest.raises((msgspec.ValidationError, TypeError)):
        msgspec.convert(value, type=MagspecPayload)
    with pytest.raises(ValidationError):
        _standard(value)


def test_unsupported_external_construct_is_not_silently_a_standard_schema() -> None:
    class Arbitrary(BaseModel):
        value: complex

    with pytest.raises(SchemaError):
        StandardSchemaAdapter().compile(Arbitrary)
