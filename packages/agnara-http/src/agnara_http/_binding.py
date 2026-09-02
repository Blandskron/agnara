"""Compiled, explicit HTTP request binding for capability inputs."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import unquote_to_bytes

from agnara.execution import ExecutionPlan

_INTEGER = re.compile(r"[+-]?\d+\Z")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
_HEADER_NAME = re.compile(rb"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")
_BAD_PERCENT = re.compile(rb"%(?![0-9A-Fa-f]{2})")

type _Message = dict[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]


class _BindingDefinitionError(ValueError):
    """A binding declaration is invalid or ambiguous."""


class _RequestBindingError(ValueError):
    """HTTP request data cannot be bound to the declared input."""

    def __init__(self, message: str, *, location: str) -> None:
        super().__init__(f"{location}: {message}")
        self.message = message
        self.location = location


class _BindingSource(StrEnum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    BODY = "body"


@dataclass(frozen=True, slots=True)
class _InputBinding:
    input_name: str
    source: _BindingSource
    wire_name: str | None = None


@dataclass(frozen=True, slots=True)
class _CompiledBinding:
    input_name: str
    source: _BindingSource
    wire_name: str
    scalar_type: str | None
    binary: bool = False


@dataclass(frozen=True, slots=True)
class _HTTPBindingPlan:
    bindings: tuple[_CompiledBinding, ...]
    max_body_bytes: int

    @classmethod
    def compile(
        cls,
        execution_plan: ExecutionPlan,
        path_parameter_names: Iterable[str],
        bindings: Iterable[_InputBinding],
        *,
        max_body_bytes: int = 1_048_576,
    ) -> _HTTPBindingPlan:
        if not isinstance(execution_plan, ExecutionPlan):
            raise _BindingDefinitionError("execution_plan must be an ExecutionPlan")
        if (
            isinstance(max_body_bytes, bool)
            or not isinstance(max_body_bytes, int)
            or max_body_bytes < 1
        ):
            raise _BindingDefinitionError("max_body_bytes must be a positive integer")

        path_names = tuple(path_parameter_names)
        if len(path_names) != len(set(path_names)):
            raise _BindingDefinitionError("path parameter names must be unique")
        declared = tuple(bindings)
        seen_inputs: set[str] = set()
        seen_wire: set[tuple[_BindingSource, str]] = set()
        body_count = 0
        compiled: list[_CompiledBinding] = []

        for binding in declared:
            if not isinstance(binding, _InputBinding):
                raise _BindingDefinitionError("bindings must contain _InputBinding values")
            if not isinstance(binding.source, _BindingSource):
                raise _BindingDefinitionError(
                    f"binding source must be a _BindingSource, got {type(binding.source).__name__}"
                )
            if binding.input_name not in execution_plan.input_schemas:
                raise _BindingDefinitionError(f"unknown capability input: {binding.input_name!r}")
            if binding.input_name in seen_inputs:
                raise _BindingDefinitionError(f"input {binding.input_name!r} has multiple sources")
            seen_inputs.add(binding.input_name)

            wire_name = binding.wire_name or binding.input_name
            if not wire_name:
                raise _BindingDefinitionError("wire names must not be empty")
            if binding.source is _BindingSource.HEADER:
                try:
                    encoded_name = wire_name.encode("ascii")
                except UnicodeEncodeError as error:
                    raise _BindingDefinitionError(
                        f"invalid HTTP header name: {wire_name!r}"
                    ) from error
                if not _HEADER_NAME.fullmatch(encoded_name):
                    raise _BindingDefinitionError(f"invalid HTTP header name: {wire_name!r}")
                wire_name = wire_name.lower()
            if binding.source is _BindingSource.PATH and wire_name not in path_names:
                raise _BindingDefinitionError(f"unknown route path parameter: {wire_name!r}")

            key = (binding.source, wire_name)
            if key in seen_wire:
                raise _BindingDefinitionError(
                    f"{binding.source.value} value {wire_name!r} binds more than one input"
                )
            seen_wire.add(key)

            scalar_type: str | None = None
            binary = False
            if binding.source is _BindingSource.BODY:
                body_count += 1
                if body_count > 1:
                    raise _BindingDefinitionError("only one JSON body input is supported")
            else:
                fragment = execution_plan.input_schemas[binding.input_name].json_schema()
                scalar = _scalar_descriptor(fragment)
                if scalar is None:
                    raise _BindingDefinitionError(
                        f"{binding.source.value} input {binding.input_name!r} "
                        "must have a scalar schema"
                    )
                scalar_type, binary = scalar
            compiled.append(
                _CompiledBinding(binding.input_name, binding.source, wire_name, scalar_type, binary)
            )

        missing = sorted(execution_plan.required_inputs.difference(seen_inputs))
        if missing:
            raise _BindingDefinitionError(f"required input {missing[0]!r} has no HTTP binding")
        bound_paths = {item.wire_name for item in compiled if item.source is _BindingSource.PATH}
        unbound_paths = sorted(set(path_names).difference(bound_paths))
        if unbound_paths:
            raise _BindingDefinitionError(f"route path parameter {unbound_paths[0]!r} is not bound")
        return cls(tuple(compiled), max_body_bytes)


async def _bind_request(
    plan: _HTTPBindingPlan,
    *,
    path_parameters: Mapping[str, str],
    query_string: bytes,
    headers: Iterable[tuple[bytes, bytes]],
    receive: _Receive,
) -> dict[str, Any]:
    """Extract one request payload; semantic validation remains in core."""
    query = _parse_query(query_string)
    header_values = _parse_headers(headers)
    payload: dict[str, Any] = {}
    body_binding = next(
        (item for item in plan.bindings if item.source is _BindingSource.BODY), None
    )

    for binding in plan.bindings:
        if binding.source is _BindingSource.BODY:
            continue
        source: Mapping[str, list[str]]
        if binding.source is _BindingSource.PATH:
            source = {name: [value] for name, value in path_parameters.items()}
        elif binding.source is _BindingSource.QUERY:
            source = query
        else:
            source = header_values
        values = source.get(binding.wire_name)
        if values is None:
            continue
        if len(values) != 1:
            raise _RequestBindingError(
                "duplicate scalar value", location=f"{binding.source.value}.{binding.wire_name}"
            )
        payload[binding.input_name] = _convert_scalar(values[0], binding)

    if body_binding is not None:
        content_types = header_values.get("content-type", [])
        if (
            len(content_types) != 1
            or content_types[0].split(";", 1)[0].strip().lower() != "application/json"
        ):
            raise _RequestBindingError("expected application/json", location="header.content-type")
        raw_body = await _read_body(receive, plan.max_body_bytes)
        if raw_body:
            try:
                text = raw_body.decode("utf-8")
                payload[body_binding.input_name] = json.loads(
                    text,
                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
                    object_pairs_hook=_object_without_duplicates,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                raise _RequestBindingError("invalid UTF-8 JSON body", location="body") from error
    return payload


def _parse_query(raw: bytes) -> dict[str, list[str]]:
    if not isinstance(raw, bytes):
        raise _RequestBindingError("query string must be bytes", location="query")
    values: dict[str, list[str]] = {}
    for pair in raw.split(b"&") if raw else ():
        name, separator, value = pair.partition(b"=")
        if _BAD_PERCENT.search(name) or _BAD_PERCENT.search(value):
            raise _RequestBindingError("invalid percent encoding", location="query")
        try:
            decoded_name = unquote_to_bytes(name.replace(b"+", b" ")).decode("utf-8")
            decoded_value = unquote_to_bytes(value.replace(b"+", b" ")).decode("utf-8")
        except UnicodeDecodeError as error:
            raise _RequestBindingError("invalid UTF-8", location="query") from error
        values.setdefault(decoded_name, []).append(decoded_value if separator else "")
    return values


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for name, item in pairs:
        if name in value:
            raise ValueError(f"duplicate JSON object key: {name}")
        value[name] = item
    return value


def _parse_headers(headers: Iterable[tuple[bytes, bytes]]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for name, value in headers:
        if (
            not isinstance(name, bytes)
            or not isinstance(value, bytes)
            or not _HEADER_NAME.fullmatch(name)
        ):
            raise _RequestBindingError("invalid raw header", location="headers")
        values.setdefault(name.decode("ascii").lower(), []).append(value.decode("latin-1"))
    return values


def _convert_scalar(value: str, binding: _CompiledBinding) -> Any:
    location = f"{binding.source.value}.{binding.wire_name}"
    try:
        if binding.binary:
            return value.encode("latin-1")
        if binding.scalar_type == "string":
            return value
        if binding.scalar_type == "integer" and _INTEGER.fullmatch(value):
            return int(value)
        if binding.scalar_type == "number" and _NUMBER.fullmatch(value):
            number = float(value)
            if math.isfinite(number):
                return number
        if binding.scalar_type == "boolean" and value in {"true", "false"}:
            return value == "true"
    except UnicodeEncodeError, OverflowError, ValueError:
        pass
    raise _RequestBindingError(f"invalid {binding.scalar_type} value", location=location)


async def _read_body(receive: _Receive, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if not isinstance(message, dict):
            raise _RequestBindingError("ASGI event must be a dictionary", location="body")
        message_type = message.get("type")
        if message_type == "http.disconnect":
            raise _RequestBindingError("client disconnected", location="body")
        if message_type != "http.request":
            raise _RequestBindingError("unexpected ASGI event", location="body")
        chunk = message.get("body", b"")
        if not isinstance(chunk, bytes):
            raise _RequestBindingError("ASGI body chunk must be bytes", location="body")
        size += len(chunk)
        if size > limit:
            raise _RequestBindingError("request body exceeds configured limit", location="body")
        chunks.append(chunk)
        more = message.get("more_body", False)
        if not isinstance(more, bool):
            raise _RequestBindingError("ASGI more_body must be boolean", location="body")
        if not more:
            return b"".join(chunks)


def _scalar_descriptor(fragment: Mapping[str, Any]) -> tuple[str, bool] | None:
    """Return the HTTP scalar shape, accepting a scalar-or-null schema."""
    candidate = fragment
    alternatives = fragment.get("anyOf")
    if isinstance(alternatives, list):
        non_null = [
            item for item in alternatives if isinstance(item, dict) and item.get("type") != "null"
        ]
        nulls = [
            item for item in alternatives if isinstance(item, dict) and item.get("type") == "null"
        ]
        if len(non_null) != 1 or len(nulls) != 1 or len(alternatives) != 2:
            return None
        candidate = non_null[0]
    scalar_type = candidate.get("type")
    if scalar_type not in {"string", "integer", "number", "boolean"}:
        return None
    return scalar_type, scalar_type == "string" and candidate.get("format") == "binary"
