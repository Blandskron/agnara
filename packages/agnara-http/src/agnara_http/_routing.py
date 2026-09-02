"""Deterministic startup registration and immutable HTTP route matching."""

from __future__ import annotations

import keyword
import re
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

_METHOD_TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")


class _RouteDefinitionError(ValueError):
    """Raised when a route declaration is malformed or ambiguous."""


class _DuplicateRouteError(_RouteDefinitionError):
    """Raised when one method has two equivalent route shapes."""


class _RouteRegistryFrozenError(RuntimeError):
    """Raised when registration is attempted after startup compilation."""


@dataclass(frozen=True, slots=True)
class _Route[T]:
    """One validated HTTP exposure target."""

    method: str
    path_template: str
    target: T
    _segments: tuple[str | None, ...] = field(repr=False)
    _parameter_names: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class _RouteMatch[T]:
    """A matched route and its raw, decoded path-segment captures."""

    route: _Route[T]
    path_parameters: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "path_parameters",
            MappingProxyType(dict(self.path_parameters)),
        )


@dataclass(slots=True)
class _BuildingNode[T]:
    static: dict[str, _BuildingNode[T]] = field(default_factory=dict)
    parameter: _BuildingNode[T] | None = None
    route: _Route[T] | None = None


@dataclass(frozen=True, slots=True)
class _FrozenNode[T]:
    static: Mapping[str, _FrozenNode[T]]
    parameter: _FrozenNode[T] | None
    route: _Route[T] | None


def _normalize_method(method: str) -> str:
    if not isinstance(method, str):
        raise _RouteDefinitionError(f"HTTP method must be a string, got {type(method).__name__}")
    if not _METHOD_TOKEN.fullmatch(method):
        raise _RouteDefinitionError(f"invalid HTTP method token: {method!r}")
    return method.upper()


def _path_segments(path: str) -> tuple[str, ...]:
    if not isinstance(path, str):
        raise _RouteDefinitionError(f"route path must be a string, got {type(path).__name__}")
    if not path.startswith("/"):
        raise _RouteDefinitionError(f"route path must start with '/': {path!r}")
    if path == "/":
        return ()
    return tuple(path[1:].split("/"))


def _parse_template(path_template: str) -> tuple[tuple[str | None, ...], tuple[str, ...]]:
    segments: list[str | None] = []
    parameter_names: list[str] = []

    for segment in _path_segments(path_template):
        if segment.startswith("{") and segment.endswith("}"):
            name = segment[1:-1]
            if not name.isidentifier() or keyword.iskeyword(name):
                raise _RouteDefinitionError(
                    f"route parameter must be a non-keyword Python identifier: {segment!r}"
                )
            if name in parameter_names:
                raise _RouteDefinitionError(
                    f"route parameter {name!r} appears more than once in {path_template!r}"
                )
            segments.append(None)
            parameter_names.append(name)
            continue
        if "{" in segment or "}" in segment:
            raise _RouteDefinitionError(
                f"route parameters must occupy a complete path segment: {segment!r}"
            )
        segments.append(segment)

    return tuple(segments), tuple(parameter_names)


def _freeze_node[T](node: _BuildingNode[T]) -> _FrozenNode[T]:
    return _FrozenNode(
        static=MappingProxyType(
            {segment: _freeze_node(child) for segment, child in node.static.items()}
        ),
        parameter=_freeze_node(node.parameter) if node.parameter is not None else None,
        route=node.route,
    )


def _compile_roots[T](routes: tuple[_Route[T], ...]) -> Mapping[str, _FrozenNode[T]]:
    roots: dict[str, _BuildingNode[T]] = {}
    for route in routes:
        node = roots.setdefault(route.method, _BuildingNode())
        for segment in route._segments:
            if segment is None:
                if node.parameter is None:
                    node.parameter = _BuildingNode()
                node = node.parameter
            else:
                node = node.static.setdefault(segment, _BuildingNode())
        node.route = route
    return MappingProxyType({method: _freeze_node(root) for method, root in roots.items()})


def _match_node[T](
    node: _FrozenNode[T],
    segments: tuple[str, ...],
    index: int,
    captures: tuple[str, ...],
) -> tuple[_Route[T], tuple[str, ...]] | None:
    if index == len(segments):
        if node.route is None:
            return None
        return node.route, captures

    segment = segments[index]
    static_node = node.static.get(segment)
    if static_node is not None:
        static_match = _match_node(static_node, segments, index + 1, captures)
        if static_match is not None:
            return static_match

    if node.parameter is not None and segment:
        return _match_node(node.parameter, segments, index + 1, (*captures, segment))
    return None


class _FrozenRouteRegistry[T]:
    """Immutable compiled route snapshot shared by request handlers without locks."""

    __slots__ = ("_method_order", "_roots", "_routes")

    def __init__(self, routes: tuple[_Route[T], ...]) -> None:
        self._routes = routes
        self._roots = _compile_roots(routes)
        self._method_order = tuple(dict.fromkeys(route.method for route in routes))

    def __iter__(self) -> Iterator[_Route[T]]:
        return iter(self._routes)

    def __len__(self) -> int:
        return len(self._routes)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({len(self)} routes)"

    def match(self, method: str, path: str) -> _RouteMatch[T] | None:
        normalized_method = _normalize_method(method)
        segments = _path_segments(path)
        root = self._roots.get(normalized_method)
        if root is None:
            return None
        matched = _match_node(root, segments, 0, ())
        if matched is None:
            return None
        route, captures = matched
        return _RouteMatch(
            route=route,
            path_parameters=dict(zip(route._parameter_names, captures, strict=True)),
        )

    def allowed_methods(self, path: str) -> tuple[str, ...]:
        segments = _path_segments(path)
        return tuple(
            method
            for method in self._method_order
            if _match_node(self._roots[method], segments, 0, ()) is not None
        )


class _RouteRegistry[T]:
    """Thread-safe startup collector for private HTTP routes."""

    __slots__ = ("_collision_keys", "_frozen", "_lock", "_routes", "_snapshot")

    def __init__(self) -> None:
        self._routes: list[_Route[T]] = []
        self._collision_keys: dict[tuple[str, tuple[str | None, ...]], _Route[T]] = {}
        self._frozen = False
        self._snapshot: _FrozenRouteRegistry[T] | None = None
        self._lock = threading.Lock()

    @property
    def is_frozen(self) -> bool:
        with self._lock:
            return self._frozen

    def __iter__(self) -> Iterator[_Route[T]]:
        with self._lock:
            return iter(tuple(self._routes))

    def __len__(self) -> int:
        with self._lock:
            return len(self._routes)

    def __repr__(self) -> str:
        with self._lock:
            state = "frozen" if self._frozen else "open"
            count = len(self._routes)
        return f"{type(self).__name__}({count} routes, {state})"

    def register(self, method: str, path_template: str, target: T) -> _Route[T]:
        normalized_method = _normalize_method(method)
        segments, parameter_names = _parse_template(path_template)
        route = _Route(
            method=normalized_method,
            path_template=path_template,
            target=target,
            _segments=segments,
            _parameter_names=parameter_names,
        )
        collision_key = (normalized_method, segments)

        with self._lock:
            if self._frozen:
                raise _RouteRegistryFrozenError(
                    f"cannot register {normalized_method} {path_template} after route freeze"
                )
            existing = self._collision_keys.get(collision_key)
            if existing is not None:
                raise _DuplicateRouteError(
                    f"route {normalized_method} {path_template!r} conflicts with already "
                    f"registered template {existing.path_template!r}"
                )
            self._routes.append(route)
            self._collision_keys[collision_key] = route
        return route

    def freeze(self) -> _FrozenRouteRegistry[T]:
        with self._lock:
            if self._snapshot is None:
                self._snapshot = _FrozenRouteRegistry(tuple(self._routes))
            self._frozen = True
            return self._snapshot
