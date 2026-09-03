"""Configurable schema, documentation and Explorer HTTP routes (E6.13)."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.core.di.resolver import DIContainer
from agnara.execution import ExecutionPlan
from agnara_http._binding import _BindingSource, _InputBinding
from agnara_http._dispatch import _compile_exposures, _HTTPDispatcher, _HTTPExposure
from agnara_http._routing import _RouteRegistry
from agnara_http._surfaces import (
    _compile_surfaces,
    _HTTPSurface,
    _SurfaceDefinitionError,
    _SurfaceDispatcher,
)


def plan(handler: Callable[..., Any], name: str = "capability") -> ExecutionPlan:
    return ExecutionPlan.compile(
        CapabilityDefinition(CapabilityId("surfaces", name), handler), DIRegistry()
    )


def capability_routes(*exposures: _HTTPExposure):
    return _compile_exposures(exposures)


def surface(
    name: str = "schema",
    path: str = "/openapi.json",
    *,
    media_type: str = "application/json",
    body: bytes = b'{"openapi":"3.2.0"}',
    headers: tuple[tuple[bytes, bytes], ...] = (),
) -> _HTTPSurface:
    return _HTTPSurface(name, path, media_type, body, headers)


def request(
    served: _SurfaceDispatcher,
    method: str,
    path: str,
    *,
    root_path: str = "",
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    pending = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    asyncio.run(
        served(
            {
                "type": "http",
                "method": method,
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": root_path,
                "headers": [],
            },
            receive,
            send,
        )
    )
    return events


class Fallback:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], Any, Any]] = []

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        self.calls.append((scope, receive, send))
        await send({"type": "http.response.start", "status": 299, "headers": []})
        await send({"type": "http.response.body", "body": b"fallback", "more_body": False})


def dispatcher(*surfaces: _HTTPSurface) -> tuple[_SurfaceDispatcher, Fallback]:
    fallback = Fallback()
    routes = _compile_surfaces(surfaces, capability_routes())
    return _SurfaceDispatcher(routes, fallback), fallback


# --- explicit descriptors -------------------------------------------------


def test_a_surface_path_has_no_implicit_default() -> None:
    parameter = inspect.signature(_HTTPSurface).parameters["path"]
    assert parameter.default is inspect.Parameter.empty


@pytest.mark.parametrize("name", ["", "Schema", "9schema", "schema route", "docs:swagger"])
def test_a_surface_needs_a_stable_logical_name(name: str) -> None:
    with pytest.raises(_SurfaceDefinitionError, match="invalid HTTP surface name"):
        surface(name=name)


@pytest.mark.parametrize("path", ["openapi.json", "/docs/{provider}", "/{page}"])
def test_a_surface_needs_an_explicit_static_absolute_path(path: str) -> None:
    with pytest.raises(_SurfaceDefinitionError, match=r"must start|must be static"):
        surface(path=path)


@pytest.mark.parametrize(
    "media_type", ["", "text", " text/html", "text/html ", "tëxt/html", "text/html\r\nx: y"]
)
def test_a_surface_needs_a_safe_media_type(media_type: str) -> None:
    with pytest.raises(_SurfaceDefinitionError, match="media_type"):
        surface(media_type=media_type)


def test_a_surface_body_is_bytes() -> None:
    with pytest.raises(_SurfaceDefinitionError, match="body must be bytes"):
        surface(body="not bytes")  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ([(b"cache-control", b"no-store")], "byte-pair tuples"),
        (((b"Cache-Control", b"no-store"),), "lowercase HTTP token"),
        (((b"content-type", b"text/plain"),), "owned by the response boundary"),
        (((b"content-length", b"7"),), "owned by the response boundary"),
        (((b"x-test", b"ok\r\nevil: yes"),), "contains control bytes"),
        (((b"x-test", b"one"), (b"x-test", b"two")), "duplicate surface header"),
    ],
)
def test_unsafe_or_ambiguous_surface_headers_are_refused(headers: Any, message: str) -> None:
    with pytest.raises(_SurfaceDefinitionError, match=message):
        surface(headers=headers)


# --- deterministic compilation and collisions -----------------------------


def test_schema_documentation_and_explorer_compile_in_stable_path_order() -> None:
    declared = (
        surface("explorer", "/agnara", media_type="text/html", body=b"explorer"),
        surface("schema", "/openapi.json"),
        surface("documentation.swagger", "/docs", media_type="text/html", body=b"docs"),
    )

    first = _compile_surfaces(declared, capability_routes())
    second = _compile_surfaces(reversed(declared), capability_routes())

    assert [(route.path_template, route.target.name) for route in first] == [
        ("/agnara", "explorer"),
        ("/docs", "documentation.swagger"),
        ("/openapi.json", "schema"),
    ]
    assert [(route.path_template, route.target.name) for route in second] == [
        (route.path_template, route.target.name) for route in first
    ]


def test_duplicate_logical_names_fail_independently_of_registration_order() -> None:
    declared = (surface("schema", "/a"), surface("schema", "/b"))

    messages = []
    for order in (declared, tuple(reversed(declared))):
        with pytest.raises(_SurfaceDefinitionError) as raised:
            _compile_surfaces(order, capability_routes())
        messages.append(str(raised.value))

    assert messages == ["duplicate HTTP surface name 'schema': /a, /b"] * 2


def test_duplicate_paths_name_both_surfaces_independently_of_registration_order() -> None:
    declared = (surface("schema", "/contract"), surface("explorer", "/contract"))

    messages = []
    for order in (declared, tuple(reversed(declared))):
        with pytest.raises(_SurfaceDefinitionError) as raised:
            _compile_surfaces(order, capability_routes())
        messages.append(str(raised.value))

    assert messages == [
        "HTTP surfaces 'explorer' and 'schema' both reserve '/contract'",
        "HTTP surfaces 'explorer' and 'schema' both reserve '/contract'",
    ]


@pytest.mark.parametrize("method", ["GET", "HEAD", "POST"])
def test_a_surface_reserves_its_path_against_every_capability_method(method: str) -> None:
    def handler() -> None:
        return None

    routes = capability_routes(_HTTPExposure(method, "/docs", plan(handler, "show_docs")))

    with pytest.raises(_SurfaceDefinitionError) as raised:
        _compile_surfaces((surface("documentation.swagger", "/docs"),), routes)

    assert str(raised.value) == (
        "HTTP surface 'documentation.swagger' at '/docs' conflicts with capability "
        f"'surfaces.show_docs' at {method} '/docs'"
    )


def test_static_surface_and_parameter_capability_routes_are_not_ambiguous() -> None:
    def handler(page: str) -> str:
        return page

    routes = capability_routes(
        _HTTPExposure(
            "GET",
            "/docs/{page}",
            plan(handler, "page"),
            (_InputBinding("page", _BindingSource.PATH),),
        )
    )
    compiled = _compile_surfaces((surface("documentation.swagger", "/docs"),), routes)
    assert len(compiled) == 1


def test_a_literal_surface_path_cannot_be_shadowed_by_a_capability_parameter() -> None:
    def handler(page: str) -> str:
        return page

    routes = capability_routes(
        _HTTPExposure(
            "POST",
            "/docs/{page}",
            plan(handler, "page"),
            (_InputBinding("page", _BindingSource.PATH),),
        )
    )

    with pytest.raises(_SurfaceDefinitionError) as raised:
        _compile_surfaces((surface("documentation.swagger", "/docs/current"),), routes)

    assert str(raised.value) == (
        "HTTP surface 'documentation.swagger' at '/docs/current' conflicts with capability "
        "'surfaces.page' at POST '/docs/{page}'"
    )


def test_capability_collision_diagnostic_is_independent_of_registration_order() -> None:
    def handler() -> None:
        return None

    declared = (
        _HTTPExposure("POST", "/docs", plan(handler, "write_docs")),
        _HTTPExposure("GET", "/docs", plan(handler, "read_docs")),
    )
    messages = []
    for order in (declared, tuple(reversed(declared))):
        with pytest.raises(_SurfaceDefinitionError) as raised:
            _compile_surfaces(
                (surface("documentation.swagger", "/docs"),), capability_routes(*order)
            )
        messages.append(str(raised.value))

    assert (
        messages
        == [
            "HTTP surface 'documentation.swagger' at '/docs' conflicts with capability "
            "'surfaces.read_docs' at GET '/docs'"
        ]
        * 2
    )


def test_a_non_exposure_capability_registry_is_refused_with_a_diagnostic() -> None:
    invalid = _RouteRegistry[str]()
    invalid.register("GET", "/ping", "not an exposure")
    with pytest.raises(_SurfaceDefinitionError, match="compiled HTTP exposures"):
        _compile_surfaces((surface(),), invalid.freeze())  # ty: ignore[invalid-argument-type]


# --- dispatch --------------------------------------------------------------


def test_get_serves_the_declared_bytes_media_type_and_safe_headers() -> None:
    served, fallback = dispatcher(
        surface(
            "documentation.swagger",
            "/docs",
            media_type="text/html; charset=utf-8",
            body=b"<title>Agnara</title>",
            headers=((b"x-content-type-options", b"nosniff"), (b"cache-control", b"no-store")),
        )
    )

    events = request(served, "GET", "/docs")

    assert events == [
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
                (b"content-length", b"21"),
                (b"cache-control", b"no-store"),
                (b"x-content-type-options", b"nosniff"),
            ],
        },
        {"type": "http.response.body", "body": b"<title>Agnara</title>", "more_body": False},
    ]
    assert fallback.calls == []


def test_head_keeps_get_headers_and_sends_no_body() -> None:
    served, _ = dispatcher(surface(body=b"1234567"))
    get_events = request(served, "GET", "/openapi.json")
    head_events = request(served, "HEAD", "/openapi.json")

    assert head_events[0] == get_events[0]
    assert head_events[1]["body"] == b""
    assert dict(head_events[0]["headers"])[b"content-length"] == b"7"


def test_method_tokens_are_normalized_for_a_surface() -> None:
    served, _ = dispatcher(surface(body=b"schema"))
    assert request(served, "get", "/openapi.json")[1]["body"] == b"schema"


def test_an_invalid_method_token_is_refused_consistently() -> None:
    served, _ = dispatcher(surface())
    with pytest.raises(ValueError, match="invalid HTTP method token"):
        request(served, "GET SCHEMA", "/openapi.json")


def test_other_methods_receive_405_with_get_and_head_allowed() -> None:
    served, fallback = dispatcher(surface())
    events = request(served, "POST", "/openapi.json")

    assert events[0]["status"] == 405
    assert dict(events[0]["headers"])[b"allow"] == b"GET, HEAD"
    assert json.loads(events[1]["body"])["instance"] == "/openapi.json"
    assert fallback.calls == []


def test_problem_type_configuration_is_detached_from_mutable_input() -> None:
    fallback = Fallback()
    problem_types = {"method_not_allowed": "https://problems.test/original"}
    served = _SurfaceDispatcher(
        _compile_surfaces((surface(),), capability_routes()),
        fallback,
        problem_types=problem_types,
    )
    problem_types["method_not_allowed"] = "https://problems.test/mutated"

    events = request(served, "POST", "/openapi.json")
    assert json.loads(events[1]["body"])["type"] == "https://problems.test/original"


def test_an_unmatched_path_delegates_the_original_exchange_unchanged() -> None:
    served, fallback = dispatcher(surface())
    events = request(served, "POST", "/capability", root_path="/api")

    assert events[0]["status"] == 299
    assert events[1]["body"] == b"fallback"
    assert len(fallback.calls) == 1
    scope, receive, send = fallback.calls[0]
    assert scope["path"] == "/capability"
    assert scope["root_path"] == "/api"
    assert callable(receive)
    assert callable(send)


def test_an_unmatched_surface_path_reaches_the_real_capability_dispatcher() -> None:
    def ping() -> dict[str, bool]:
        return {"ok": True}

    capabilities = capability_routes(_HTTPExposure("GET", "/ping", plan(ping, "ping")))
    served = _SurfaceDispatcher(
        _compile_surfaces((surface(),), capabilities),
        _HTTPDispatcher(capabilities, DIContainer(DIRegistry())),
    )

    events = request(served, "GET", "/ping")
    assert events[0]["status"] == 200
    assert json.loads(events[1]["body"]) == {"ok": True}


def test_root_path_is_stripped_before_surface_matching() -> None:
    served, fallback = dispatcher(surface("documentation.swagger", "/docs", body=b"docs"))

    assert request(served, "GET", "/api/docs", root_path="/api")[1]["body"] == b"docs"
    assert fallback.calls == []


def test_trailing_slash_remains_significant() -> None:
    served, fallback = dispatcher(surface("documentation.swagger", "/docs", body=b"docs"))

    assert request(served, "GET", "/docs/")[0]["status"] == 299
    assert len(fallback.calls) == 1


def test_constructor_rejects_uncompiled_routes_and_non_callable_fallback() -> None:
    routes = _compile_surfaces((), capability_routes())
    with pytest.raises(TypeError, match="routes must be a frozen registry"):
        _SurfaceDispatcher(object(), Fallback())  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError, match="fallback must be callable"):
        _SurfaceDispatcher(routes, object())  # ty: ignore[invalid-argument-type]
