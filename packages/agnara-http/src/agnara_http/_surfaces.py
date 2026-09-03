"""Compiled HTTP routes for already-produced schema and documentation surfaces.

This layer deliberately knows nothing about OpenAPI projection, documentation
providers or Agnara Explorer.  It receives complete bytes that an earlier,
security-sensitive publication step already decided may be served, reserves
their explicit paths at startup, and emits them without runtime reflection.

Omitting a surface is configuration, not authorization.  Authorization and
viewer-specific filtering must happen before a surface reaches this module.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from agnara_http._dispatch import (
    _CompiledExposure,
    _problem_instance,
    _routed_path,
)
from agnara_http._problem import (
    _ABOUT_BLANK_TYPES,
    _allow_header,
    _serialize_transport_failure,
    _TransportFailure,
)
from agnara_http._response import _send_response, _SerializedResponse
from agnara_http._routing import (
    _FrozenRouteRegistry,
    _normalize_method,
    _parse_template,
    _RouteRegistry,
)

type _Scope = dict[str, Any]
type _Message = dict[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]
type _Send = Callable[[_Message], Awaitable[None]]
type _HTTPDispatch = Callable[[_Scope, _Receive, _Send], Awaitable[None]]

_SURFACE_NAME = re.compile(r"[a-z][a-z0-9._-]*\Z")
_HEADER_NAME = re.compile(rb"[!#$%&'*+\-.^_`|~0-9a-z]+\Z")
_RESERVED_HEADERS = frozenset({b"content-length", b"content-type"})


class _SurfaceDefinitionError(ValueError):
    """A schema, documentation or Explorer route is unsafe or ambiguous."""


@dataclass(frozen=True, slots=True)
class _HTTPSurface:
    """One explicitly named static HTTP surface.

    ``path`` has no default on purpose.  RFC 0003 keeps familiar paths such as
    ``/openapi.json`` and ``/docs`` provisional until the public composition
    API is reviewed.
    """

    name: str
    path: str
    media_type: str
    body: bytes
    headers: tuple[tuple[bytes, bytes], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _SURFACE_NAME.fullmatch(self.name):
            raise _SurfaceDefinitionError(f"invalid HTTP surface name: {self.name!r}")
        try:
            segments, parameters = _parse_template(self.path)
        except (TypeError, ValueError) as error:
            raise _SurfaceDefinitionError(str(error)) from error
        if parameters or any(segment is None for segment in segments):
            raise _SurfaceDefinitionError(f"HTTP surface path must be static, got {self.path!r}")
        if (
            not isinstance(self.media_type, str)
            or not self.media_type.strip()
            or self.media_type != self.media_type.strip()
        ):
            raise _SurfaceDefinitionError("surface media_type must be a non-empty string")
        try:
            encoded_media_type = self.media_type.encode("ascii")
        except UnicodeEncodeError as error:
            raise _SurfaceDefinitionError("surface media_type must be ASCII") from error
        if b"/" not in encoded_media_type or _has_control(encoded_media_type):
            raise _SurfaceDefinitionError(f"invalid surface media_type: {self.media_type!r}")
        if not isinstance(self.body, bytes):
            raise _SurfaceDefinitionError("surface body must be bytes")
        if not isinstance(self.headers, tuple):
            raise _SurfaceDefinitionError("surface headers must be byte-pair tuples")

        names: set[bytes] = set()
        for pair in self.headers:
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not isinstance(pair[0], bytes)
                or not isinstance(pair[1], bytes)
            ):
                raise _SurfaceDefinitionError("surface headers must be byte-pair tuples")
            name, value = pair
            if not _HEADER_NAME.fullmatch(name):
                raise _SurfaceDefinitionError(
                    f"surface header name must be a lowercase HTTP token: {name!r}"
                )
            if name in _RESERVED_HEADERS:
                raise _SurfaceDefinitionError(
                    f"surface header {name.decode('ascii')!r} is owned by the response boundary"
                )
            if name in names:
                raise _SurfaceDefinitionError(f"duplicate surface header: {name!r}")
            if _has_control(value):
                raise _SurfaceDefinitionError(f"surface header {name!r} contains control bytes")
            names.add(name)


@dataclass(frozen=True, slots=True)
class _CompiledSurface:
    """One immutable startup-validated surface response."""

    name: str
    response: _SerializedResponse


def _compile_surfaces(
    surfaces: Iterable[_HTTPSurface],
    capability_routes: _FrozenRouteRegistry[_CompiledExposure],
) -> _FrozenRouteRegistry[_CompiledSurface]:
    """Compile surfaces in stable order and reserve their paths application-wide."""
    if not isinstance(capability_routes, _FrozenRouteRegistry):
        raise TypeError(
            f"capability_routes must be a frozen registry, got {type(capability_routes).__name__}"
        )
    declared = tuple(surfaces)
    if any(not isinstance(surface, _HTTPSurface) for surface in declared):
        raise _SurfaceDefinitionError("surfaces must contain only _HTTPSurface values")
    ordered = tuple(sorted(declared, key=lambda surface: (surface.name, surface.path)))
    _check_unique_names(ordered)
    _check_reserved_paths(ordered, capability_routes)

    registry: _RouteRegistry[_CompiledSurface] = _RouteRegistry()
    for surface in sorted(ordered, key=lambda item: (item.path, item.name)):
        response_headers = (
            (b"content-type", surface.media_type.encode("ascii")),
            (b"content-length", str(len(surface.body)).encode("ascii")),
            *sorted(surface.headers),
        )
        registry.register(
            "GET",
            surface.path,
            _CompiledSurface(
                surface.name,
                _SerializedResponse(200, response_headers, surface.body),
            ),
        )
    return registry.freeze()


def _check_unique_names(surfaces: tuple[_HTTPSurface, ...]) -> None:
    by_name: dict[str, list[str]] = {}
    for surface in surfaces:
        by_name.setdefault(surface.name, []).append(surface.path)
    for name in sorted(by_name):
        paths = sorted(by_name[name])
        if len(paths) > 1:
            raise _SurfaceDefinitionError(
                f"duplicate HTTP surface name {name!r}: {', '.join(paths)}"
            )


def _check_reserved_paths(
    surfaces: tuple[_HTTPSurface, ...],
    capability_routes: _FrozenRouteRegistry[_CompiledExposure],
) -> None:
    surface_paths: dict[str, _HTTPSurface] = {}
    for surface in surfaces:
        existing = surface_paths.get(surface.path)
        if existing is not None:
            first, second = sorted((existing.name, surface.name))
            raise _SurfaceDefinitionError(
                f"HTTP surfaces {first!r} and {second!r} both reserve {surface.path!r}"
            )
        surface_paths[surface.path] = surface

    capability_route_list = tuple(
        sorted(capability_routes, key=lambda item: (item.method, item.path_template))
    )
    for route in capability_route_list:
        if not isinstance(route.target, _CompiledExposure):
            raise _SurfaceDefinitionError("capability_routes must contain compiled HTTP exposures")

    methods = tuple(sorted({route.method for route in capability_route_list}))
    for surface in surfaces:
        for method in methods:
            match = capability_routes.match(method, surface.path)
            if match is None:
                continue
            route = match.route
            capability_id = route.target.plan.definition.id
            raise _SurfaceDefinitionError(
                f"HTTP surface {surface.name!r} at {surface.path!r} conflicts with capability "
                f"{str(capability_id)!r} at {route.method} {route.path_template!r}"
            )


class _SurfaceDispatcher:
    """Serve compiled static surfaces, delegating every other path unchanged."""

    __slots__ = ("_fallback", "_problem_types", "_routes")

    def __init__(
        self,
        routes: _FrozenRouteRegistry[_CompiledSurface],
        fallback: _HTTPDispatch,
        *,
        problem_types: Mapping[str, str] = _ABOUT_BLANK_TYPES,
    ) -> None:
        if not isinstance(routes, _FrozenRouteRegistry):
            raise TypeError(f"routes must be a frozen registry, got {type(routes).__name__}")
        if not callable(fallback):
            raise TypeError(f"fallback must be callable, got {type(fallback).__name__}")
        if not isinstance(problem_types, Mapping):
            raise TypeError("problem_types must be a mapping")
        self._routes = routes
        self._fallback = fallback
        self._problem_types = MappingProxyType(dict(problem_types))

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        method = scope.get("method")
        if not isinstance(method, str):
            raise TypeError("ASGI scope 'method' must be a string")
        normalized_method = _normalize_method(method)
        path = _routed_path(scope)
        match = self._routes.match("GET", path)
        if match is None:
            await self._fallback(scope, receive, send)
            return
        if normalized_method in {"GET", "HEAD"}:
            await _send_response(
                match.route.target.response,
                send,
                head=normalized_method == "HEAD",
            )
            return
        response = _serialize_transport_failure(
            _TransportFailure.METHOD_NOT_ALLOWED,
            "the target does not accept this method",
            headers=_allow_header(("GET", "HEAD")),
            problem_types=self._problem_types,
            instance=_problem_instance(path),
        )
        await _send_response(response, send)


def _has_control(value: bytes) -> bool:
    return any(byte < 0x20 or byte == 0x7F for byte in value)
