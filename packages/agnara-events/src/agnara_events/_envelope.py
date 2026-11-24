"""Strict CloudEvents 1.0 structured-mode JSON decoder (ADR 0101, EVT-03)."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

__all__: list[str] = []

CLOUDEVENTS_JSON_CONTENT_TYPE = "application/cloudevents+json"
JSON_DATA_CONTENT_TYPE = "application/json"
MAX_BODY_BYTES = 65_536
MAX_JSON_DEPTH = 32


class _EnvelopeError(ValueError):
    """Redacted CloudEvents envelope or strict JSON failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class _DecodedCloudEvent:
    """Validated ADR 0101 CloudEvents 1.0 envelope and decoded ``data`` object."""

    specversion: str
    event_type: str
    source: str
    event_id: str
    data: Mapping[str, Any]


def _check_json_depth(text: str, max_depth: int) -> None:
    """Reject JSON nesting deeper than ``max_depth`` linearly without recursion."""
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
            if depth > max_depth:
                raise _EnvelopeError("json_nesting_depth")
        elif ch in "}]":
            depth -= 1


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _EnvelopeError("duplicate_key")
        result[key] = value
    return result


def _reject_constant(token: str) -> Any:
    raise _EnvelopeError("non_finite_number")


def _parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise _EnvelopeError("non_finite_number")
    return value


def _parse_bounded_int(token: str) -> int:
    try:
        return int(token)
    except ValueError as error:
        raise _EnvelopeError("integer_bounds") from error


def _parse_strict_json(
    raw_body: bytes,
    *,
    max_bytes: int = MAX_BODY_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
) -> Any:
    """Enforce body size, strict UTF-8, depth bound, unique keys, and finite numbers."""
    if not isinstance(raw_body, bytes):
        raise _EnvelopeError("malformed_body")
    if len(raw_body) > max_bytes:
        raise _EnvelopeError("body_too_large")
    try:
        text = raw_body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise _EnvelopeError("invalid_utf8") from error

    _check_json_depth(text, max_depth)

    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_parse_finite_float,
            parse_int=_parse_bounded_int,
        )
    except _EnvelopeError:
        raise
    except ValueError as error:
        raise _EnvelopeError("malformed_json") from error


def _is_valid_uri_reference(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        return False
    try:
        urlsplit(value)
    except ValueError:
        return False
    return True


def _decode_cloudevent(
    body: bytes,
    content_type: str | None,
    *,
    expected_type: str,
    max_bytes: int = MAX_BODY_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
) -> _DecodedCloudEvent:
    """Decode one structured CloudEvents 1.0 JSON message matching ``expected_type``."""
    if content_type != CLOUDEVENTS_JSON_CONTENT_TYPE:
        raise _EnvelopeError("unsupported_content_type")

    parsed = _parse_strict_json(body, max_bytes=max_bytes, max_depth=max_depth)
    if type(parsed) is not dict:
        raise _EnvelopeError("invalid_envelope")
    if parsed.get("specversion") != "1.0":
        raise _EnvelopeError("invalid_specversion")
    if parsed.get("type") != expected_type:
        raise _EnvelopeError("type_mismatch")
    if "data_base64" in parsed:
        raise _EnvelopeError("unsupported_data_base64")
    if "datacontenttype" in parsed and parsed["datacontenttype"] != JSON_DATA_CONTENT_TYPE:
        raise _EnvelopeError("unsupported_datacontenttype")

    event_id = parsed.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise _EnvelopeError("invalid_id")
    source = parsed.get("source")
    if not _is_valid_uri_reference(source):
        raise _EnvelopeError("invalid_source")
    assert isinstance(source, str)

    data = parsed.get("data")
    if type(data) is not dict:
        raise _EnvelopeError("invalid_data")

    return _DecodedCloudEvent(
        specversion="1.0",
        event_type=expected_type,
        source=source,
        event_id=event_id,
        data=MappingProxyType(dict(data)),
    )
