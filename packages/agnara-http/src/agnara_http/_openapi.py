"""Deterministic OpenAPI 3.2 projection from compiled HTTP exposures.

The module is internal until the HTTP composition API is reviewed. It consumes
only the immutable registry used by request dispatch and plain JSON Schema data
from core's schema port. OpenAPI vocabulary stays in this adapter.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from agnara_http._binding import _BindingSource
from agnara_http._dispatch import _CompiledExposure
from agnara_http._routing import _FrozenRouteRegistry, _parse_template

_OPENAPI_VERSION = "3.2.0"
_OAS_DIALECT = "https://spec.openapis.org/oas/3.1/dialect/base"
_OPERATION_METHODS = frozenset(
    {"GET", "PUT", "POST", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE", "QUERY"}
)
_RESERVED_PARAMETER_HEADERS = frozenset({"accept", "authorization", "content-type"})
_PATH_LITERAL = re.compile(r"(?:[A-Za-z0-9._~!$&'()*+,;=:@-]|%[0-9A-Fa-f]{2})+\Z")


class _OpenAPIDefinitionError(ValueError):
    """A compiled HTTP application cannot be represented truthfully in OpenAPI."""


@dataclass(frozen=True, slots=True)
class _OpenAPIInfo:
    """Required document metadata, kept separate from capability semantics."""

    title: str
    version: str
    summary: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("title", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise _OpenAPIDefinitionError(f"OpenAPI info {field_name} must be non-empty")
        for field_name in ("summary", "description"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise _OpenAPIDefinitionError(
                    f"OpenAPI info {field_name} must be a non-empty string or None"
                )


def _project_openapi(
    routes: _FrozenRouteRegistry[_CompiledExposure],
    info: _OpenAPIInfo,
) -> dict[str, Any]:
    """Project an already-compiled registry, filtering before assembly."""
    if not isinstance(routes, _FrozenRouteRegistry):
        raise TypeError(f"routes must be a frozen registry, got {type(routes).__name__}")
    if not isinstance(info, _OpenAPIInfo):
        raise TypeError(f"info must be _OpenAPIInfo, got {type(info).__name__}")

    paths: dict[str, dict[str, Any]] = {}
    operation_ids: set[str] = set()
    for route in routes:
        exposure = route.target
        if not isinstance(exposure, _CompiledExposure):
            raise _OpenAPIDefinitionError("route target is not a compiled HTTP exposure")
        publication = exposure.openapi
        if publication is None:
            # Security-sensitive order: an unpublished exposure contributes no
            # path, identifier, description, tag, or schema fragment.
            continue
        if route.method not in _OPERATION_METHODS:
            raise _OpenAPIDefinitionError(
                f"HTTP method {route.method!r} has no OpenAPI 3.2 Path Item field"
            )
        _validate_path(route.path_template)
        operation_id = _operation_id(
            str(exposure.plan.definition.id), route.method, route.path_template
        )
        if operation_id in operation_ids:  # pragma: no cover - route identity makes this defensive
            raise _OpenAPIDefinitionError(f"duplicate OpenAPI operationId: {operation_id!r}")
        operation_ids.add(operation_id)
        paths.setdefault(route.path_template, {})[route.method.lower()] = _operation(
            exposure, operation_id, route.method
        )

    info_object: dict[str, Any] = {"title": info.title, "version": info.version}
    if info.summary is not None:
        info_object["summary"] = info.summary
    if info.description is not None:
        info_object["description"] = info.description
    return {
        "openapi": _OPENAPI_VERSION,
        "jsonSchemaDialect": _OAS_DIALECT,
        "info": info_object,
        "paths": paths,
        "components": {"schemas": {"Problem": _problem_schema()}},
    }


def _operation(
    exposure: _CompiledExposure,
    operation_id: str,
    method: str,
) -> dict[str, Any]:
    publication = exposure.openapi
    if publication is None:  # pragma: no cover - filtered by _project_openapi
        raise _OpenAPIDefinitionError("an unpublished exposure has no OpenAPI operation")
    operation: dict[str, Any] = {
        "operationId": operation_id,
        "responses": _responses(method),
    }
    if publication.summary is not None:
        operation["summary"] = publication.summary
    description = exposure.plan.definition.description
    if publication.publish_description and description is not None:
        operation["description"] = description
    if publication.tags:
        operation["tags"] = list(publication.tags)
    if publication.deprecated:
        operation["deprecated"] = True

    parameters: list[dict[str, Any]] = []
    for binding in exposure.binding.bindings:
        schema = _schema_value(exposure.plan.input_schemas[binding.input_name].json_schema())
        if binding.source is _BindingSource.BODY:
            operation["requestBody"] = {
                "required": binding.input_name in exposure.plan.required_inputs,
                "content": {"application/json": {"schema": schema}},
            }
            continue
        if (
            binding.source is _BindingSource.HEADER
            and binding.wire_name in _RESERVED_PARAMETER_HEADERS
        ):
            raise _OpenAPIDefinitionError(
                f"header {binding.wire_name!r} cannot be represented as an OpenAPI parameter"
            )
        parameter: dict[str, Any] = {
            "name": binding.wire_name,
            "in": binding.source.value,
            "required": (
                binding.source is _BindingSource.PATH
                or binding.input_name in exposure.plan.required_inputs
            ),
            "schema": schema,
        }
        parameters.append(parameter)
    if parameters:
        operation["parameters"] = parameters
    return operation


def _responses(method: str) -> dict[str, Any]:
    """Describe exactly the adapter's current non-streaming output boundary."""
    success: dict[str, Any] = {"description": "Successful capability result."}
    if method != "HEAD":
        success["content"] = {"application/json": {"schema": {}}}
    return {
        "200": success,
        "204": {"description": "Successful capability result with no value."},
        "default": {
            "description": "Capability or HTTP request problem.",
            "content": {
                "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
            },
        },
    }


def _problem_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["type", "title", "status", "code", "detail"],
        "properties": {
            "type": {"type": "string", "format": "uri-reference"},
            "title": {"type": "string"},
            "status": {"type": "integer", "minimum": 100, "maximum": 599},
            "code": {"type": "string"},
            "detail": {"type": "string"},
            "details": {},
            "instance": {"type": "string", "format": "uri-reference"},
        },
    }


def _operation_id(capability_id: str, method: str, path_template: str) -> str:
    return f"{capability_id}:{method.lower()}:{path_template}"


def _validate_path(path_template: str) -> None:
    segments, _ = _parse_template(path_template)
    for segment in segments:
        if segment is None:
            continue
        if not _PATH_LITERAL.fullmatch(segment):
            raise _OpenAPIDefinitionError(
                f"route path is not an OpenAPI 3.2 path template: {path_template!r}"
            )


def _schema_value(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _OpenAPIDefinitionError("schema port returned a non-mapping JSON Schema")
    copied = _json_value(value, set(), path="$schema")
    if not isinstance(copied, dict):  # pragma: no cover - Mapping input guarantees this
        raise _OpenAPIDefinitionError("schema port returned a non-object JSON Schema")
    return copied


def _json_value(value: object, active: set[int], *, path: str) -> Any:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _OpenAPIDefinitionError(f"{path}: non-finite number")
        return value
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise _OpenAPIDefinitionError(f"{path}: cyclic schema")
        active.add(identity)
        try:
            copied: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise _OpenAPIDefinitionError(f"{path}: schema keys must be strings")
                copied[key] = _json_value(item, active, path=f"{path}.{key}")
            return copied
        finally:
            active.remove(identity)
    if isinstance(value, list | tuple):
        identity = id(value)
        if identity in active:
            raise _OpenAPIDefinitionError(f"{path}: cyclic schema")
        active.add(identity)
        try:
            return [
                _json_value(item, active, path=f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        finally:
            active.remove(identity)
    raise _OpenAPIDefinitionError(f"{path}: value is not JSON-compatible")


def _serialize_openapi(document: Mapping[str, Any]) -> bytes:
    """Serialize one projected document as deterministic compact UTF-8 JSON."""
    if not isinstance(document, Mapping):
        raise TypeError(f"document must be a mapping, got {type(document).__name__}")
    plain = _json_value(document, set(), path="$")
    try:
        return json.dumps(
            plain,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:  # pragma: no cover - defensive
        raise _OpenAPIDefinitionError("OpenAPI document is not valid UTF-8 JSON") from error
