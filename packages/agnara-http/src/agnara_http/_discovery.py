"""The authorized machine-readable discovery endpoint.

Every other surface in this package serves bytes an earlier step already
decided may be served. This one cannot: the document depends on who is asking,
so the filtering happens per request, against the principal this request
resolved to, before anything is serialized.

That makes three things load-bearing rather than decorative.

Authorization is required, not optional. The endpoint takes a principal
resolver, and an unidentified viewer gets ``401`` unless the composer opted
into anonymous discovery in so many words.

A filtered document must never be reused across viewers. A ``public`` cache
directive is refused at startup, and ``Vary`` is always sent, so a shared
cache cannot hand one viewer's document to another.

Failure is closed. A resolver that raises produces a redacted ``500``: no
partially filtered document, and no traceback reaching the client.

Seeing a capability here still authorizes nothing. Invocation runs the normal
policy pipeline, and this endpoint neither consults nor bypasses it.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from agnara.introspection import DiscoveryVisibility, IntrospectionSnapshot, filter_snapshot
from agnara.policy import AnonymousPrincipal, Principal
from agnara_http._dispatch import _CompiledExposure, _problem_instance, _routed_path
from agnara_http._problem import (
    _ABOUT_BLANK_TYPES,
    _INTERNAL_PROBLEM,
    _allow_header,
    _serialize_transport_failure,
    _TransportFailure,
)
from agnara_http._response import _send_response, _SerializedResponse
from agnara_http._routing import _FrozenRouteRegistry, _normalize_method, _parse_template

type _Scope = dict[str, Any]
type _Message = dict[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]
type _Send = Callable[[_Message], Awaitable[None]]
type _HTTPDispatch = Callable[[_Scope, _Receive, _Send], Awaitable[None]]

_JSON_MEDIA_TYPE = b"application/json"

#: The conservative default. A discovery document is cheap to rebuild and
#: expensive to leak, so nothing is stored unless a composer says otherwise.
_DEFAULT_CACHE_CONTROL = "private, no-store"

#: Sent with every response. Even under ``no-store`` it costs nothing, and it
#: is the header that stays correct if a composer later relaxes the directive.
_DEFAULT_VARY: tuple[str, ...] = ("Authorization",)

#: Cache directives that would let one viewer's filtered document be served to
#: another. Refused at startup rather than at request time.
_FORBIDDEN_CACHE_DIRECTIVES = frozenset({"public", "s-maxage", "immutable"})


class _DiscoveryDefinitionError(ValueError):
    """A discovery endpoint configuration is unsafe or ambiguous."""


@runtime_checkable
class _PrincipalResolver(Protocol):
    """Turn one ASGI scope into the principal that request speaks for.

    Returning ``None`` means the request carried no identity this application
    recognises. It does not mean "allow anonymously": that is the composer's
    separate decision.

    The resolver is the application's authentication boundary. This package
    verifies no credential and interprets no header; it only asks.
    """

    def __call__(self, scope: _Scope, /) -> Principal | None: ...


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise _DiscoveryDefinitionError(f"discovery {field} must be a non-empty trimmed string")
    return value


def _ascii_header(value: str, *, field: str) -> bytes:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as error:
        raise _DiscoveryDefinitionError(f"discovery {field} must be ASCII") from error
    if any(byte < 0x20 or byte == 0x7F for byte in encoded):
        raise _DiscoveryDefinitionError(f"discovery {field} contains control bytes")
    return encoded


@dataclass(frozen=True, slots=True)
class _DiscoveryRoute:
    """One declared discovery endpoint, validated before it can serve anything.

    ``path`` has no default, for the reason RFC 0003 gives for every other
    surface: a familiar path is a composition decision, not a framework one.
    """

    path: str
    snapshot: IntrospectionSnapshot
    visibility: DiscoveryVisibility
    principals: _PrincipalResolver
    challenge: str | None = None
    allow_anonymous: bool = False
    cache_control: str = _DEFAULT_CACHE_CONTROL
    vary: tuple[str, ...] = _DEFAULT_VARY

    def __post_init__(self) -> None:
        _text(self.path, field="path")
        try:
            segments, parameters = _parse_template(self.path)
        except (TypeError, ValueError) as error:
            raise _DiscoveryDefinitionError(str(error)) from error
        if parameters or any(segment is None for segment in segments):
            raise _DiscoveryDefinitionError(f"discovery path must be static, got {self.path!r}")
        if not isinstance(self.snapshot, IntrospectionSnapshot):
            raise _DiscoveryDefinitionError("discovery snapshot must be an IntrospectionSnapshot")
        if not isinstance(self.visibility, DiscoveryVisibility):
            raise _DiscoveryDefinitionError("discovery visibility must be a DiscoveryVisibility")
        if not callable(self.principals):
            raise _DiscoveryDefinitionError("discovery principals must be callable")
        if not isinstance(self.allow_anonymous, bool):
            raise _DiscoveryDefinitionError("allow_anonymous must be a boolean")
        if self.allow_anonymous:
            if self.challenge is not None:
                raise _DiscoveryDefinitionError(
                    "an anonymous discovery endpoint must not declare a challenge, because it "
                    "never answers 401"
                )
        else:
            # RFC 9110 requires WWW-Authenticate on a 401, so an endpoint that
            # can produce one must say how a client should authenticate.
            _ascii_header(_text(self.challenge, field="challenge"), field="challenge")
        _validate_cache_control(self.cache_control)
        if not isinstance(self.vary, tuple) or not self.vary:
            raise _DiscoveryDefinitionError(
                "discovery vary must be a non-empty tuple of header names"
            )
        for name in self.vary:
            _ascii_header(_text(name, field="vary header"), field="vary header")


def _validate_cache_control(value: object) -> None:
    _text(value, field="cache_control")
    assert isinstance(value, str)
    _ascii_header(value, field="cache_control")
    directives = {part.strip().split("=", 1)[0].lower() for part in value.split(",")}
    forbidden = sorted(directives & _FORBIDDEN_CACHE_DIRECTIVES)
    if forbidden:
        raise _DiscoveryDefinitionError(
            "a discovery document is viewer-specific, so it must not be shared-cacheable: "
            f"remove {', '.join(forbidden)}"
        )


@dataclass(frozen=True, slots=True)
class _CompiledDiscovery:
    """A discovery route whose headers and path are fixed at startup."""

    path: str
    snapshot: IntrospectionSnapshot
    visibility: DiscoveryVisibility
    principals: _PrincipalResolver
    allow_anonymous: bool
    headers: tuple[tuple[bytes, bytes], ...]
    challenge_headers: tuple[tuple[bytes, bytes], ...]


def _compile_discovery(
    route: _DiscoveryRoute,
    capability_routes: _FrozenRouteRegistry[_CompiledExposure],
) -> _CompiledDiscovery:
    """Validate the route and reserve its path against every capability route."""
    if not isinstance(route, _DiscoveryRoute):
        raise _DiscoveryDefinitionError(
            f"discovery route must be a _DiscoveryRoute, got {type(route).__name__}"
        )
    if not isinstance(capability_routes, _FrozenRouteRegistry):
        raise TypeError(
            f"capability_routes must be a frozen registry, got {type(capability_routes).__name__}"
        )
    for existing in sorted(capability_routes, key=lambda item: (item.method, item.path_template)):
        match = capability_routes.match(existing.method, route.path)
        if match is None:
            continue
        capability_id = match.route.target.plan.definition.id
        raise _DiscoveryDefinitionError(
            f"discovery path {route.path!r} conflicts with capability {str(capability_id)!r} "
            f"at {match.route.method} {match.route.path_template!r}"
        )

    headers = (
        (b"cache-control", _ascii_header(route.cache_control, field="cache_control")),
        (b"vary", ", ".join(route.vary).encode("ascii")),
    )
    challenge_headers: tuple[tuple[bytes, bytes], ...] = ()
    if route.challenge is not None:
        challenge_headers = ((b"www-authenticate", route.challenge.encode("ascii")),)
    return _CompiledDiscovery(
        path=route.path,
        snapshot=route.snapshot,
        visibility=route.visibility,
        principals=route.principals,
        allow_anonymous=route.allow_anonymous,
        headers=headers,
        challenge_headers=challenge_headers,
    )


class _DiscoveryDispatcher:
    """Serve one discovery route, delegating every other path unchanged."""

    __slots__ = ("_fallback", "_problem_types", "_route")

    def __init__(
        self,
        route: _CompiledDiscovery,
        fallback: _HTTPDispatch,
        *,
        problem_types: Mapping[str, str] = _ABOUT_BLANK_TYPES,
    ) -> None:
        if not isinstance(route, _CompiledDiscovery):
            raise TypeError(f"route must be a compiled discovery, got {type(route).__name__}")
        if not callable(fallback):
            raise TypeError(f"fallback must be callable, got {type(fallback).__name__}")
        if not isinstance(problem_types, Mapping):
            raise TypeError("problem_types must be a mapping")
        self._route = route
        self._fallback = fallback
        self._problem_types = MappingProxyType(dict(problem_types))

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        method = scope.get("method")
        if not isinstance(method, str):
            raise TypeError("ASGI scope 'method' must be a string")
        path = _routed_path(scope)
        if path != self._route.path:
            await self._fallback(scope, receive, send)
            return

        normalized = _normalize_method(method)
        if normalized not in {"GET", "HEAD"}:
            await _send_response(self._method_not_allowed(path), send)
            return

        principal = _principal_or_failure(self._route, scope)
        if principal is None:
            await _send_response(self._unauthenticated(path), send, head=normalized == "HEAD")
            return
        if isinstance(principal, _ResolverFailed):
            await _send_response(self._internal(), send, head=normalized == "HEAD")
            return

        document = filter_snapshot(self._route.snapshot, self._route.visibility, principal)
        body = json.dumps(
            document.json_data(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        response = _SerializedResponse(
            200,
            (
                (b"content-type", _JSON_MEDIA_TYPE),
                (b"content-length", str(len(body)).encode("ascii")),
                *self._route.headers,
            ),
            body,
        )
        await _send_response(response, send, head=normalized == "HEAD")

    def _method_not_allowed(self, path: str) -> _SerializedResponse:
        return _serialize_transport_failure(
            _TransportFailure.METHOD_NOT_ALLOWED,
            "the target does not accept this method",
            headers=_allow_header(("GET", "HEAD")),
            problem_types=self._problem_types,
            instance=_problem_instance(path),
        )

    def _unauthenticated(self, path: str) -> _SerializedResponse:
        return _serialize_transport_failure(
            _TransportFailure.UNAUTHENTICATED,
            "discovery requires an identified viewer",
            headers=self._challenge_headers(),
            problem_types=self._problem_types,
            instance=_problem_instance(path),
        )

    def _challenge_headers(self) -> Iterable[tuple[bytes, bytes]]:
        return self._route.challenge_headers

    def _internal(self) -> _SerializedResponse:
        """The shared last-resort 500.

        A resolver that raised, or returned something that is not a principal,
        is a server defect. The client learns that and nothing else: reporting
        it as ``401`` would invite a retry that cannot help, and reporting the
        cause would describe the authentication boundary's internals.
        """
        return _INTERNAL_PROBLEM


@dataclass(frozen=True, slots=True)
class _ResolverFailed:
    """A resolver outcome that must not be confused with 'no identity'."""


_RESOLVER_FAILED = _ResolverFailed()


def _principal_or_failure(
    route: _CompiledDiscovery,
    scope: _Scope,
) -> Principal | _ResolverFailed | None:
    """Ask the application who is asking, keeping three outcomes distinct.

    A principal, no recognised identity, and a resolver that failed are three
    different answers, and collapsing any two of them is a security bug: a
    failed resolver read as anonymous would serve a document to a request
    nobody identified.

    Shared by every surface that serves the snapshot, so a human reading the
    Explorer and a program reading the endpoint cannot be identified
    differently for the same request.
    """
    try:
        resolved = route.principals(scope)
    except Exception:
        # The resolver is application code touching credentials. Whatever it
        # raised must not reach the client, and must not be read as anonymous.
        return _RESOLVER_FAILED
    if resolved is None:
        if route.allow_anonymous:
            return AnonymousPrincipal(metadata={"transport": "http"})
        return None
    if not isinstance(resolved, Principal):
        return _RESOLVER_FAILED
    return resolved
