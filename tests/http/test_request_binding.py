import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara_http._binding import (
    _bind_request,
    _BindingDefinitionError,
    _BindingSource,
    _HTTPBindingPlan,
    _InputBinding,
    _RequestBindingError,
)


def execution_plan(handler: Callable[..., Any]) -> ExecutionPlan:
    definition = CapabilityDefinition(CapabilityId("tests", "binding"), handler)
    return ExecutionPlan.compile(definition, DIRegistry())


def compile_plan(
    handler: Callable[..., Any],
    *bindings: _InputBinding,
    paths: tuple[str, ...] = (),
    max_body_bytes: int = 1_048_576,
) -> _HTTPBindingPlan:
    return _HTTPBindingPlan.compile(
        execution_plan(handler), paths, bindings, max_body_bytes=max_body_bytes
    )


def receiver(*messages: dict[str, Any]) -> Callable[[], Any]:
    pending = iter(messages)

    async def receive() -> dict[str, Any]:
        return next(pending)

    return receive


def test_compile_requires_explicit_complete_unique_bindings() -> None:
    def handler(user_id: int, search: str) -> None:
        pass

    with pytest.raises(_BindingDefinitionError, match="required input 'search'"):
        compile_plan(handler, _InputBinding("user_id", _BindingSource.PATH), paths=("user_id",))
    with pytest.raises(_BindingDefinitionError, match="multiple sources"):
        compile_plan(
            handler,
            _InputBinding("user_id", _BindingSource.PATH),
            _InputBinding("user_id", _BindingSource.QUERY),
            _InputBinding("search", _BindingSource.QUERY),
            paths=("user_id",),
        )


def test_compile_rejects_unknown_or_unbound_path_and_non_scalar_wire_input() -> None:
    def handler(user_id: int, tags: list[str] = []) -> None:  # noqa: B006
        pass

    with pytest.raises(_BindingDefinitionError, match="unknown route path"):
        compile_plan(handler, _InputBinding("user_id", _BindingSource.PATH), paths=("id",))
    with pytest.raises(_BindingDefinitionError, match="must have a scalar schema"):
        compile_plan(
            handler,
            _InputBinding("user_id", _BindingSource.PATH, "id"),
            _InputBinding("tags", _BindingSource.QUERY),
            paths=("id",),
        )


def test_compile_normalizes_and_validates_header_names() -> None:
    def handler(token: str) -> None:
        pass

    plan = compile_plan(handler, _InputBinding("token", _BindingSource.HEADER, "X-Token"))
    assert plan.bindings[0].wire_name == "x-token"
    with pytest.raises(_BindingDefinitionError, match="invalid HTTP header"):
        compile_plan(handler, _InputBinding("token", _BindingSource.HEADER, "bad header"))


def test_compile_accepts_nullable_scalar_wire_input() -> None:
    def handler(search: str | None = None) -> None:
        pass

    plan = compile_plan(handler, _InputBinding("search", _BindingSource.QUERY))
    assert plan.bindings[0].scalar_type == "string"


def test_binds_and_converts_path_query_and_case_insensitive_header() -> None:
    async def run_test() -> None:
        def handler(user_id: int, active: bool, token: str) -> None:
            pass

        plan = compile_plan(
            handler,
            _InputBinding("user_id", _BindingSource.PATH),
            _InputBinding("active", _BindingSource.QUERY),
            _InputBinding("token", _BindingSource.HEADER, "X-Token"),
            paths=("user_id",),
        )
        payload = await _bind_request(
            plan,
            path_parameters={"user_id": "42"},
            query_string=b"active=true",
            headers=[(b"X-Token", b"secret")],
            receive=receiver(),
        )
        assert payload == {"user_id": 42, "active": True, "token": "secret"}

    asyncio.run(run_test())


@pytest.mark.parametrize("query", [b"value=%", b"value=%GG", b"value=%FF"])
def test_rejects_malformed_or_non_utf8_query(query: bytes) -> None:
    async def run_test() -> None:
        def handler(value: str) -> None:
            pass

        plan = compile_plan(handler, _InputBinding("value", _BindingSource.QUERY))
        with pytest.raises(_RequestBindingError, match="query"):
            await _bind_request(
                plan, path_parameters={}, query_string=query, headers=[], receive=receiver()
            )

    asyncio.run(run_test())


def test_rejects_duplicate_scalar_query_values() -> None:
    async def run_test() -> None:
        def handler(value: str) -> None:
            pass

        plan = compile_plan(handler, _InputBinding("value", _BindingSource.QUERY))
        with pytest.raises(_RequestBindingError, match="duplicate scalar"):
            await _bind_request(
                plan,
                path_parameters={},
                query_string=b"value=a&value=b",
                headers=[],
                receive=receiver(),
            )

    asyncio.run(run_test())


def test_reads_chunked_json_body_with_limit() -> None:
    async def run_test() -> None:
        def handler(command: dict[str, int]) -> None:
            pass

        plan = compile_plan(
            handler, _InputBinding("command", _BindingSource.BODY), max_body_bytes=20
        )
        payload = await _bind_request(
            plan,
            path_parameters={},
            query_string=b"",
            headers=[(b"content-type", b"application/json; charset=utf-8")],
            receive=receiver(
                {"type": "http.request", "body": b'{"count":', "more_body": True},
                {"type": "http.request", "body": b"2}", "more_body": False},
            ),
        )
        assert payload == {"command": {"count": 2}}

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("headers", "messages", "message"),
    [
        ([], (), "application/json"),
        ([(b"content-type", b"text/plain")], (), "application/json"),
        (
            [(b"content-type", b"application/json")],
            ({"type": "http.disconnect"},),
            "disconnected",
        ),
        (
            [(b"content-type", b"application/json")],
            ({"type": "websocket.receive"},),
            "unexpected ASGI event",
        ),
        (
            [(b"content-type", b"application/json")],
            ({"type": "http.request", "body": b"123456", "more_body": False},),
            "exceeds configured limit",
        ),
        (
            [(b"content-type", b"application/json")],
            ({"type": "http.request", "body": b"NaN", "more_body": False},),
            "invalid UTF-8 JSON",
        ),
    ],
)
def test_rejects_invalid_body_requests(
    headers: list[tuple[bytes, bytes]], messages: tuple[dict[str, Any], ...], message: str
) -> None:
    async def run_test() -> None:
        def handler(command: int) -> None:
            pass

        plan = compile_plan(
            handler, _InputBinding("command", _BindingSource.BODY), max_body_bytes=5
        )
        with pytest.raises(_RequestBindingError, match=message):
            await _bind_request(
                plan,
                path_parameters={},
                query_string=b"",
                headers=headers,
                receive=receiver(*messages),
            )

    asyncio.run(run_test())


def test_rejects_duplicate_json_object_keys() -> None:
    async def run_test() -> None:
        def handler(command: dict[str, int]) -> None:
            pass

        plan = compile_plan(handler, _InputBinding("command", _BindingSource.BODY))
        with pytest.raises(_RequestBindingError, match="invalid UTF-8 JSON"):
            await _bind_request(
                plan,
                path_parameters={},
                query_string=b"",
                headers=[(b"content-type", b"application/json")],
                receive=receiver(
                    {
                        "type": "http.request",
                        "body": b'{"a":1,"a":2}',
                        "more_body": False,
                    }
                ),
            )

    asyncio.run(run_test())


def test_does_not_receive_when_no_body_is_bound() -> None:
    async def run_test() -> None:
        called = False

        async def receive() -> dict[str, Any]:
            nonlocal called
            called = True
            raise AssertionError

        def handler(value: str = "default") -> None:
            pass

        plan = compile_plan(handler)
        assert (
            await _bind_request(
                plan, path_parameters={}, query_string=b"", headers=[], receive=receive
            )
            == {}
        )
        assert called is False

    asyncio.run(run_test())


def test_receive_cancellation_propagates() -> None:
    async def run_test() -> None:
        async def receive() -> dict[str, Any]:
            raise asyncio.CancelledError

        def handler(command: int) -> None:
            pass

        plan = compile_plan(handler, _InputBinding("command", _BindingSource.BODY))
        with pytest.raises(asyncio.CancelledError):
            await _bind_request(
                plan,
                path_parameters={},
                query_string=b"",
                headers=[(b"content-type", b"application/json")],
                receive=receive,
            )

    asyncio.run(run_test())
