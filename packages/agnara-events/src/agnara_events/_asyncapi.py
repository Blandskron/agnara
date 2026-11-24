"""Opt-in AsyncAPI 3.1.0 projection with JSON Schema Draft-07 translation (ADR 0101, EVT-03)."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ._envelope import CLOUDEVENTS_JSON_CONTENT_TYPE, JSON_DATA_CONTENT_TYPE
from ._exposure import _CompiledEventBinding

__all__: list[str] = []

ASYNCAPI_VERSION = "3.1.0"
DRAFT_07_SCHEMA_FORMAT = "application/schema+json;version=draft-07"

_PRIMITIVE_TYPES = frozenset({"null", "boolean", "object", "array", "number", "integer", "string"})
_NUMERIC_BOUND_KEYS = frozenset(
    {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}
)
_LENGTH_BOUND_KEYS = frozenset({"minLength", "maxLength", "minItems", "maxItems"})
_ALLOWED_SCHEMA_KEYS = frozenset(
    {
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "prefixItems",
        *_NUMERIC_BOUND_KEYS,
        *_LENGTH_BOUND_KEYS,
    }
)
_TUPLE_ALLOWED_KEYS = frozenset({"type", "prefixItems", "items", "minItems", "maxItems"})


class _AsyncAPIExportError(ValueError):
    """Safe failure when a visible event exposure cannot be projected to AsyncAPI."""


@dataclass(frozen=True, slots=True)
class _AsyncAPIInfo:
    """Explicit public AsyncAPI info metadata."""

    title: str
    version: str
    summary: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("title", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise _AsyncAPIExportError(f"AsyncAPI info {field_name} must be non-empty")
        for field_name in ("summary", "description"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise _AsyncAPIExportError(
                    f"AsyncAPI info {field_name} must be non-empty when supplied"
                )


def _ensure_json_literal(value: object) -> Any:
    if value is None or isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _AsyncAPIExportError("non-finite numeric schema value is not allowed")
        return value
    if isinstance(value, list | tuple):
        return [_ensure_json_literal(item) for item in value]
    if isinstance(value, Mapping):
        checked: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _AsyncAPIExportError("schema literal mapping keys must be strings")
            checked[key] = _ensure_json_literal(item)
        return checked
    raise _AsyncAPIExportError("unsupported non-JSON schema literal")


def _non_negative_int(key: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _AsyncAPIExportError(f"schema keyword {key!r} must be a non-negative integer")
    return value


def _finite_number(key: str, value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _AsyncAPIExportError(f"schema keyword {key!r} must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise _AsyncAPIExportError(f"schema keyword {key!r} must be finite")
    if key == "multipleOf" and value <= 0:
        raise _AsyncAPIExportError("schema keyword 'multipleOf' must be positive")
    return value


def _translate_tuple(schema: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(schema) - _TUPLE_ALLOWED_KEYS
    if unknown:
        raise _AsyncAPIExportError(
            f"fixed tuple schema contains unsupported keywords: {sorted(unknown)}"
        )
    if "type" in schema and schema["type"] != "array":
        raise _AsyncAPIExportError("fixed tuple schema must declare type 'array'")
    prefix_items = schema["prefixItems"]
    if not isinstance(prefix_items, list | tuple) or not prefix_items:
        raise _AsyncAPIExportError("fixed tuple schema requires non-empty prefixItems")
    if schema.get("items") is not False:
        raise _AsyncAPIExportError("fixed tuple translation requires items: false")
    min_items = _non_negative_int("minItems", schema.get("minItems"))
    max_items = _non_negative_int("maxItems", schema.get("maxItems"))
    if min_items != len(prefix_items) or max_items != len(prefix_items):
        raise _AsyncAPIExportError("fixed tuple requires exact minItems and maxItems")
    return {
        "type": "array",
        "items": [_translate_schema_to_draft07(item) for item in prefix_items],
        "additionalItems": False,
        "minItems": min_items,
        "maxItems": max_items,
    }


def _translate_schema_to_draft07(schema: object) -> dict[str, Any] | bool:
    """Translate a restricted schema subset to JSON Schema Draft-07."""
    if isinstance(schema, bool):
        return schema
    if not isinstance(schema, Mapping):
        raise _AsyncAPIExportError("schema node must be a mapping or boolean")

    for key in schema:
        if not isinstance(key, str) or key not in _ALLOWED_SCHEMA_KEYS:
            raise _AsyncAPIExportError(f"unsupported schema keyword {key!r}")

    if "prefixItems" in schema:
        return _translate_tuple(schema)

    translated: dict[str, Any] = {}
    if "type" in schema:
        raw_type = schema["type"]
        if isinstance(raw_type, str):
            if raw_type not in _PRIMITIVE_TYPES:
                raise _AsyncAPIExportError(f"unsupported schema type {raw_type!r}")
            translated["type"] = raw_type
        elif isinstance(raw_type, list | tuple) and raw_type:
            seen: list[str] = []
            for item in raw_type:
                if not isinstance(item, str) or item not in _PRIMITIVE_TYPES or item in seen:
                    raise _AsyncAPIExportError("unsupported schema type list")
                seen.append(item)
            translated["type"] = seen
        else:
            raise _AsyncAPIExportError("unsupported schema type declaration")

    if "enum" in schema:
        enum_values = schema["enum"]
        if not isinstance(enum_values, list | tuple) or not enum_values:
            raise _AsyncAPIExportError("schema enum must be a non-empty list")
        translated["enum"] = [_ensure_json_literal(item) for item in enum_values]

    if "const" in schema:
        translated["const"] = _ensure_json_literal(schema["const"])

    for key in _NUMERIC_BOUND_KEYS:
        if key in schema:
            translated[key] = _finite_number(key, schema[key])

    for key in _LENGTH_BOUND_KEYS:
        if key in schema:
            translated[key] = _non_negative_int(key, schema[key])

    if "properties" in schema:
        raw_props = schema["properties"]
        if not isinstance(raw_props, Mapping):
            raise _AsyncAPIExportError("schema properties must be a mapping")
        # Property names are application field identifiers, never schema keywords.
        translated["properties"] = {
            name: _translate_schema_to_draft07(prop_schema)
            for name, prop_schema in _validated_property_entries(raw_props)
        }

    if "required" in schema:
        raw_required = schema["required"]
        if not isinstance(raw_required, list | tuple) or not all(
            isinstance(item, str) for item in raw_required
        ):
            raise _AsyncAPIExportError("schema required must be a list of strings")
        translated["required"] = list(raw_required)

    if "additionalProperties" in schema:
        additional = schema["additionalProperties"]
        if isinstance(additional, bool):
            translated["additionalProperties"] = additional
        elif isinstance(additional, Mapping):
            translated["additionalProperties"] = _translate_schema_to_draft07(additional)
        else:
            raise _AsyncAPIExportError("schema additionalProperties must be a boolean or schema")

    if "items" in schema:
        items_schema = schema["items"]
        if not isinstance(items_schema, bool | Mapping):
            raise _AsyncAPIExportError("homogeneous array items must be a schema or boolean")
        translated["items"] = _translate_schema_to_draft07(items_schema)

    return translated


def _validated_property_entries(raw_props: Mapping[Any, Any]) -> list[tuple[str, Any]]:
    entries: list[tuple[str, Any]] = []
    for name, prop_schema in raw_props.items():
        if not isinstance(name, str):
            raise _AsyncAPIExportError("schema property names must be strings")
        entries.append((name, prop_schema))
    return entries


def _data_object_schema(binding: _CompiledEventBinding) -> dict[str, Any]:
    plan = binding.plan
    protected = plan.protected_parameters
    properties: dict[str, Any] = {}
    for name, schema in plan.input_schemas.items():
        if name in protected:
            continue
        properties[name] = _translate_schema_to_draft07(schema.json_schema())
    required = sorted(name for name in plan.required_inputs if name not in protected)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _envelope_schema(event_type: str, data_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "specversion": {"type": "string", "const": "1.0"},
            "id": {"type": "string", "minLength": 1},
            "source": {"type": "string", "minLength": 1},
            "type": {"type": "string", "const": event_type},
            "datacontenttype": {"type": "string", "const": JSON_DATA_CONTENT_TYPE},
            "data": data_schema,
        },
        "required": ["specversion", "id", "source", "type", "data"],
        "additionalProperties": True,
    }


def _project_asyncapi(
    bindings: _CompiledEventBinding | Iterable[_CompiledEventBinding],
    info: _AsyncAPIInfo,
    *,
    is_visible: Callable[[_CompiledEventBinding], bool] | None = None,
) -> dict[str, Any]:
    """Project visible inbound bindings into a detached AsyncAPI 3.1.0 document."""
    if not isinstance(info, _AsyncAPIInfo):
        raise _AsyncAPIExportError("info must be an _AsyncAPIInfo")
    binding_list = [bindings] if isinstance(bindings, _CompiledEventBinding) else list(bindings)

    channels: dict[str, Any] = {}
    operations: dict[str, Any] = {}
    messages: dict[str, Any] = {}
    seen_addresses: set[str] = set()

    for binding in binding_list:
        if not isinstance(binding, _CompiledEventBinding):
            raise _AsyncAPIExportError("bindings must contain _CompiledEventBinding values")
        exposure = binding.exposure
        # Security-sensitive order: filter private or hidden exposures before
        # building or translating schemas so hidden entries never leak into errors.
        if exposure.public_address is None:
            continue
        if is_visible is not None and not is_visible(binding):
            continue

        subscription_id = exposure.subscription_id
        if subscription_id in channels:
            raise _AsyncAPIExportError(f"duplicate visible subscription_id {subscription_id!r}")
        if exposure.public_address in seen_addresses:
            raise _AsyncAPIExportError("duplicate visible public_address")
        seen_addresses.add(exposure.public_address)

        data_schema = _data_object_schema(binding)
        message_name = f"{subscription_id}Message"
        message_object: dict[str, Any] = {
            "name": message_name,
            "contentType": CLOUDEVENTS_JSON_CONTENT_TYPE,
            "payload": {
                "schemaFormat": DRAFT_07_SCHEMA_FORMAT,
                "schema": _envelope_schema(exposure.event_type, data_schema),
            },
        }
        if exposure.summary is not None:
            message_object["summary"] = exposure.summary
        if exposure.description is not None:
            message_object["description"] = exposure.description
        messages[message_name] = message_object

        channels[subscription_id] = {
            "address": exposure.public_address,
            "messages": {
                message_name: {"$ref": f"#/components/messages/{message_name}"},
            },
        }
        operation_id = f"receive_{subscription_id}"
        operation_object: dict[str, Any] = {
            "action": "receive",
            "channel": {"$ref": f"#/channels/{subscription_id}"},
            "messages": [{"$ref": f"#/channels/{subscription_id}/messages/{message_name}"}],
        }
        if exposure.summary is not None:
            operation_object["summary"] = exposure.summary
        if exposure.description is not None:
            operation_object["description"] = exposure.description
        operations[operation_id] = operation_object

    info_object: dict[str, Any] = {"title": info.title, "version": info.version}
    if info.summary is not None:
        info_object["summary"] = info.summary
    if info.description is not None:
        info_object["description"] = info.description

    document = {
        "asyncapi": ASYNCAPI_VERSION,
        "info": info_object,
        "defaultContentType": CLOUDEVENTS_JSON_CONTENT_TYPE,
        "channels": channels,
        "operations": operations,
        "components": {"messages": messages},
    }
    try:
        serialized = json.dumps(document, allow_nan=False)
    except ValueError as error:
        raise _AsyncAPIExportError("AsyncAPI document is not JSON-serializable") from error
    return json.loads(serialized)
