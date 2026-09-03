"""Compiled HTTP exposures and the request path that uses them.

This is the module that turns the adapter's separate pieces into a request:
routing (E6.2), binding (E6.3), success responses (E6.4), capability failure
problems (E6.5) and transport problems (E6.6a).

Everything reflective happens at compilation. Dispatch does a trie lookup, a
binding pass over already-classified sources, one core invocation and one
serialization, against an immutable registry that needs no lock.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agnara.core.di.resolver import DIContainer
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation, invoke_result
from agnara_http._binding import (
    _bind_request,
    _BindingDefinitionError,
    _BindingFailure,
    _HTTPBindingPlan,
    _InputBinding,
    _RequestBindingError,
)
from agnara_http._problem import (
    _ABOUT_BLANK_TYPES,
    _INTERNAL_PROBLEM,
    _allow_header,
    _serialize_result,
    _serialize_transport_failure,
    _TransportFailure,
)
from agnara_http._response import (
    _ResponseSerializationError,
    _send_response,
    _SerializedResponse,
)
from agnara_http._routing import (
    _FrozenRouteRegistry,
    _parse_template,
    _RouteRegistry,
)

type _Scope = dict[str, Any]
type _Message = dict[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]
type _Send = Callable[[_Message], Awaitable[None]]

#: A binding failure that can still be answered, and the status it earns.
#: ``DISCONNECTED`` is absent because there is nobody left to answer.
_BINDING_STATUS: Mapping[_BindingFailure, _TransportFailure] = {
    _BindingFailure.MALFORMED: _TransportFailure.INVALID_INPUT,
    _BindingFailure.UNSUPPORTED_MEDIA_TYPE: _TransportFailure.UNSUPPORTED_MEDIA_TYPE,
    _BindingFailure.CONTENT_TOO_LARGE: _TransportFailure.CONTENT_TOO_LARGE,
}


@dataclass(frozen=True, slots=True)
class _OpenAPIPublication:
    """Metadata an exposure explicitly permits the OpenAPI projection to use."""

    summary: str | None = None
    publish_description: bool = False
    tags: tuple[str, ...] = ()
    deprecated: bool = False

    def __post_init__(self) -> None:
        if self.summary is not None and (
            not isinstance(self.summary, str) or not self.summary.strip()
        ):
            raise _BindingDefinitionError("OpenAPI summary must be a non-empty string or None")
        if not isinstance(self.publish_description, bool):
            raise _BindingDefinitionError("publish_description must be a boolean")
        if not isinstance(self.tags, tuple):
            raise _BindingDefinitionError("OpenAPI tags must be a tuple")
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise _BindingDefinitionError("OpenAPI tags must be non-empty strings")
        if len(self.tags) != len(set(self.tags)):
            raise _BindingDefinitionError("OpenAPI tags must be unique")
        if not isinstance(self.deprecated, bool):
            raise _BindingDefinitionError("deprecated must be a boolean")


@dataclass(frozen=True, slots=True)
class _HTTPExposure:
    """One declared HTTP exposure of a compiled capability."""

    method: str
    path_template: str
    plan: ExecutionPlan
    bindings: tuple[_InputBinding, ...] = ()
    max_body_bytes: int = 1_048_576
    openapi: _OpenAPIPublication | None = None


@dataclass(frozen=True, slots=True)
class _CompiledExposure:
    """What a matched route resolves to, in one lookup."""

    plan: ExecutionPlan
    binding: _HTTPBindingPlan
    openapi: _OpenAPIPublication | None


def _compile_exposures(
    exposures: Iterable[_HTTPExposure],
) -> _FrozenRouteRegistry[_CompiledExposure]:
    """Validate and freeze every exposure before the first request arrives."""
    registry: _RouteRegistry[_CompiledExposure] = _RouteRegistry()
    for exposure in exposures:
        if not isinstance(exposure, _HTTPExposure):
            raise _BindingDefinitionError(
                f"exposures must contain _HTTPExposure values, got {type(exposure).__name__}"
            )
        if exposure.openapi is not None and not isinstance(exposure.openapi, _OpenAPIPublication):
            raise _BindingDefinitionError("openapi must be _OpenAPIPublication or None")
        _, parameter_names = _parse_template(exposure.path_template)
        binding = _HTTPBindingPlan.compile(
            exposure.plan,
            parameter_names,
            exposure.bindings,
            max_body_bytes=exposure.max_body_bytes,
        )
        registry.register(
            exposure.method,
            exposure.path_template,
            _CompiledExposure(exposure.plan, binding, exposure.openapi),
        )
    return registry.freeze()


@dataclass(frozen=True, slots=True)
class _DispatchOptions:
    """Everything the request path needs that is not an exposure."""

    problem_types: Mapping[str, str] = field(default_factory=lambda: _ABOUT_BLANK_TYPES)
    timeout: float | None = None

    def __post_init__(self) -> None:
        if self.timeout is not None and (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, int | float)
            or self.timeout <= 0
        ):
            raise ValueError("timeout must be a positive number of seconds or None")


class _HTTPDispatcher:
    """Serve one HTTP request from an immutable compiled route registry.

    Every invocation runs as the anonymous principal. Authentication is not
    designed yet, which is also why no path here can produce a ``401``.
    """

    __slots__ = ("_container", "_options", "_routes")

    def __init__(
        self,
        routes: _FrozenRouteRegistry[_CompiledExposure],
        di_container: DIContainer,
        options: _DispatchOptions | None = None,
    ) -> None:
        if not isinstance(routes, _FrozenRouteRegistry):
            raise TypeError(f"routes must be a frozen registry, got {type(routes).__name__}")
        if not isinstance(di_container, DIContainer):
            raise TypeError(
                f"di_container must be a DIContainer, got {type(di_container).__name__}"
            )
        self._routes = routes
        self._container = di_container
        self._options = options if options is not None else _DispatchOptions()

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        method = scope.get("method")
        if not isinstance(method, str):
            raise TypeError("ASGI scope 'method' must be a string")
        path = _routed_path(scope)
        head = method == "HEAD"
        instance = _problem_instance(path)

        match = self._routes.match(method, path)
        if match is None and head:
            # HEAD is implied by GET: same headers, no body.
            match = self._routes.match("GET", path)
        if match is None:
            await _send_response(self._not_matched(path, instance), send, head=head)
            return

        exposure = match.route.target
        try:
            payload = await _bind_request(
                exposure.binding,
                path_parameters=match.path_parameters,
                query_string=scope.get("query_string", b""),
                headers=scope.get("headers", ()),
                receive=receive,
            )
        except _RequestBindingError as error:
            if error.failure is _BindingFailure.DISCONNECTED:
                return
            await _send_response(self._binding_problem(error, instance), send, head=head)
            return

        result = await invoke_result(
            exposure.plan,
            ExecutionContext(
                Invocation(
                    capability_id=exposure.plan.definition.id,
                    payload=payload,
                    metadata={"transport": "http", "method": method, "path": path},
                    deadline=self._deadline(),
                ),
                self._container,
            ),
        )

        try:
            response = _serialize_result(
                result,
                problem_types=self._options.problem_types,
                instance=instance,
            )
        except _ResponseSerializationError:
            # Nothing has been sent yet, so the last resort is still available.
            response = _INTERNAL_PROBLEM
        await _send_response(response, send, head=head)

    def _deadline(self) -> float | None:
        timeout = self._options.timeout
        if timeout is None:
            return None
        return asyncio.get_running_loop().time() + timeout

    def _not_matched(self, path: str, instance: str | None) -> _SerializedResponse:
        allowed = _allowed_methods(self._routes, path)
        if allowed:
            return _serialize_transport_failure(
                _TransportFailure.METHOD_NOT_ALLOWED,
                "the target does not accept this method",
                headers=_allow_header(allowed),
                problem_types=self._options.problem_types,
                instance=instance,
            )
        return _serialize_transport_failure(
            _TransportFailure.NOT_FOUND,
            "no capability is exposed at this target",
            problem_types=self._options.problem_types,
            instance=instance,
        )

    def _binding_problem(
        self,
        error: _RequestBindingError,
        instance: str | None,
    ) -> _SerializedResponse:
        return _serialize_transport_failure(
            _BINDING_STATUS[error.failure],
            error.message,
            details={"location": error.location},
            problem_types=self._options.problem_types,
            instance=instance,
        )


def _allowed_methods(
    routes: _FrozenRouteRegistry[_CompiledExposure],
    path: str,
) -> tuple[str, ...]:
    """List the methods this target accepts, adding the HEAD implied by GET."""
    allowed = routes.allowed_methods(path)
    if "GET" not in allowed or "HEAD" in allowed:
        return allowed
    index = allowed.index("GET")
    return (*allowed[: index + 1], "HEAD", *allowed[index + 1 :])


def _routed_path(scope: _Scope) -> str:
    """Strip the mount prefix so a mounted application matches its own paths."""
    path = scope.get("path")
    if not isinstance(path, str):
        raise TypeError("ASGI scope 'path' must be a string")
    root_path = scope.get("root_path", "")
    if not isinstance(root_path, str):
        raise TypeError("ASGI scope 'root_path' must be a string")
    if not root_path:
        return path
    if path == root_path:
        return "/"
    mount_prefix = root_path if root_path.endswith("/") else f"{root_path}/"
    if not path.startswith(mount_prefix):
        return path
    remainder = path[len(root_path) :]
    return remainder if remainder.startswith("/") else f"/{remainder}"


def _problem_instance(path: str) -> str | None:
    """Return the path as a URI reference, or nothing when it cannot be one.

    The query string is deliberately excluded. A secret passed in a query
    would otherwise be copied into the problem body and into every log that
    keeps it. A target that is not usable as a URI reference yields ``None``
    rather than making a ``404`` fail to serialize.
    """
    if not path or not path.isascii():
        return None
    if any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F for character in path
    ):
        return None
    return path
