"""Deterministic JSON success serialization and ASGI response emission."""

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any

from agnara.execution import Failure, Success

type _Message = dict[str, Any]
type _Send = Callable[[_Message], Awaitable[None]]


class _ResponseSerializationError(ValueError):
    """A successful value cannot be represented by this JSON response boundary."""


@dataclass(frozen=True, slots=True)
class _SerializedResponse:
    """One complete non-streaming response, ready for ASGI emission."""

    status: int
    headers: tuple[tuple[bytes, bytes], ...]
    body: bytes

    def __post_init__(self) -> None:
        if isinstance(self.status, bool) or not isinstance(self.status, int):
            raise TypeError("response status must be an integer")
        if self.status < 100 or self.status > 999:
            raise ValueError("response status must be a three-digit HTTP status")
        if not isinstance(self.headers, tuple) or not all(
            isinstance(pair, tuple)
            and len(pair) == 2
            and isinstance(pair[0], bytes)
            and isinstance(pair[1], bytes)
            for pair in self.headers
        ):
            raise TypeError("response headers must be byte-pair tuples")
        if not isinstance(self.body, bytes):
            raise TypeError("response body must be bytes")


def _serialize_success(result: Success[Any]) -> _SerializedResponse:
    """Serialize a canonical success; failures belong to the RFC 9457 boundary."""
    if isinstance(result, Failure):
        raise _ResponseSerializationError("failure outcomes require RFC 9457 serialization")
    if not isinstance(result, Success):
        raise TypeError(f"result must be Success, got {type(result).__name__}")
    if result.value is None:
        return _SerializedResponse(status=204, headers=(), body=b"")

    plain = _to_json_value(result.value, set(), path="$")
    try:
        body = json.dumps(
            plain,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise _ResponseSerializationError("success value is not valid UTF-8 JSON") from error
    return _SerializedResponse(
        status=200,
        headers=(
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode("ascii")),
        ),
        body=body,
    )


async def _send_response(
    response: _SerializedResponse,
    send: _Send,
    *,
    head: bool = False,
) -> None:
    """Emit exactly one response start and one terminal body event."""
    if not isinstance(response, _SerializedResponse):
        raise TypeError(f"response must be _SerializedResponse, got {type(response).__name__}")
    if not callable(send):
        raise TypeError(f"send must be callable, got {type(send).__name__}")
    if not isinstance(head, bool):
        raise TypeError("head must be a boolean")
    await send(
        {
            "type": "http.response.start",
            "status": response.status,
            "headers": list(response.headers),
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b"" if head else response.body,
            "more_body": False,
        }
    )


def _to_json_value(value: object, active: set[int], *, path: str) -> Any:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _ResponseSerializationError(f"{path}: non-finite float is not JSON")
        return value
    if isinstance(value, Enum):
        return _to_json_value(value.value, active, path=path)

    track = isinstance(value, Mapping | list | tuple) or (
        is_dataclass(value) and not isinstance(value, type)
    )
    identity = id(value)
    if track:
        if identity in active:
            raise _ResponseSerializationError(f"{path}: cyclic output value")
        active.add(identity)
    try:
        if isinstance(value, Mapping):
            plain: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise _ResponseSerializationError(f"{path}: JSON object keys must be strings")
                plain[key] = _to_json_value(item, active, path=f"{path}.{key}")
            return plain
        if isinstance(value, list | tuple):
            return [
                _to_json_value(item, active, path=f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        if is_dataclass(value) and not isinstance(value, type):
            return {
                field.name: _to_json_value(
                    getattr(value, field.name), active, path=f"{path}.{field.name}"
                )
                for field in fields(value)
            }
    finally:
        if track:
            active.remove(identity)
    raise _ResponseSerializationError(f"{path}: unsupported output type {type(value).__name__}")
