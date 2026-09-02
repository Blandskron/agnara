import asyncio
from dataclasses import FrozenInstanceError, dataclass
from enum import Enum
from typing import Any

import pytest

from agnara.execution import Failure, FailureCode, Success
from agnara_http._response import (
    _ResponseSerializationError,
    _send_response,
    _serialize_success,
    _SerializedResponse,
)


class State(Enum):
    READY = "ready"


@dataclass(frozen=True, slots=True)
class Receipt:
    identifier: str
    amounts: tuple[int, ...]
    state: State


def test_serializes_structured_success_as_deterministic_compact_utf8_json() -> None:
    response = _serialize_success(
        Success(
            {
                "z": "Ñandú",
                "receipt": Receipt("r-1", (3, 2), State.READY),
                "active": True,
            }
        )
    )

    assert response.status == 200
    assert response.body == (
        b'{"active":true,"receipt":{"amounts":[3,2],"identifier":"r-1",'
        b'"state":"ready"},"z":"\xc3\x91and\xc3\xba"}'
    )
    assert response.headers == (
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(response.body)).encode("ascii")),
    )


def test_none_success_is_204_without_representation_headers() -> None:
    assert _serialize_success(Success(None)) == _SerializedResponse(204, (), b"")


def test_serialized_response_is_frozen_and_slotted() -> None:
    response = _serialize_success(Success("ok"))
    assert not hasattr(response, "__dict__")
    with pytest.raises(FrozenInstanceError):
        response.body = b"changed"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (float("nan"), "non-finite"),
        (float("inf"), "non-finite"),
        ({1: "value"}, "keys must be strings"),
        ({"value": object()}, "unsupported output type object"),
        (b"binary", "unsupported output type bytes"),
    ],
)
def test_rejects_values_outside_json_contract(value: object, message: str) -> None:
    with pytest.raises(_ResponseSerializationError, match=message):
        _serialize_success(Success(value))


def test_rejects_cyclic_output_with_path() -> None:
    value: list[Any] = []
    value.append({"nested": value})
    with pytest.raises(_ResponseSerializationError, match=r"\$\[0\]\.nested: cyclic"):
        _serialize_success(Success(value))


def test_rejects_failure_before_response_serialization() -> None:
    failure = Failure(FailureCode.NOT_FOUND, "missing")
    with pytest.raises(_ResponseSerializationError, match="RFC 9457"):
        _serialize_success(failure)  # ty: ignore[invalid-argument-type]


def test_emits_exact_asgi_start_and_terminal_body_events() -> None:
    async def run_test() -> None:
        messages: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)

        response = _serialize_success(Success({"ok": True}))
        await _send_response(response, send)

        assert messages == [
            {
                "type": "http.response.start",
                "status": 200,
                "headers": list(response.headers),
            },
            {"type": "http.response.body", "body": b'{"ok":true}', "more_body": False},
        ]

    asyncio.run(run_test())


def test_head_preserves_get_headers_but_suppresses_body_bytes() -> None:
    async def run_test() -> None:
        messages: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)

        response = _serialize_success(Success([1, 2, 3]))
        await _send_response(response, send, head=True)

        assert response.headers[-1] == (b"content-length", b"7")
        assert messages[-1] == {"type": "http.response.body", "body": b"", "more_body": False}

    asyncio.run(run_test())


def test_send_failure_and_cancellation_propagate_without_extra_events() -> None:
    async def run_test() -> None:
        response = _serialize_success(Success("ok"))
        calls = 0

        async def fail_on_body(message: dict[str, Any]) -> None:
            nonlocal calls
            calls += 1
            if message["type"] == "http.response.body":
                raise RuntimeError("send failed")

        with pytest.raises(RuntimeError, match="send failed"):
            await _send_response(response, fail_on_body)
        assert calls == 2

        async def cancel(message: dict[str, Any]) -> None:
            del message
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await _send_response(response, cancel)

    asyncio.run(run_test())
