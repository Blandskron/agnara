"""Agnara Explorer: the filtered snapshot, for a person to read.

RFC 0003 section 6 is explicit that this is not another OpenAPI skin. Its data
source is the protocol-neutral snapshot, which is why it can show a capability
reachable through MCP and A2A — the thing an OpenAPI viewer structurally
cannot.

The shell is server-rendered HTML with no JavaScript, no stylesheet and no
external asset. That is not minimalism for its own sake:

*Read-only becomes structural.* There is no client code that could be made to
write, and no interactive surface to secure. RFC 0003 requires interactive
execution to be a separate decision from viewing; here it is not merely
separate, it is absent.

*The content security policy can be maximally strict.* `default-src 'none'`
with no exceptions is honest only because the page genuinely loads nothing.
Adding a stylesheet later is a real decision with a real CSP consequence, and
it should be made as one rather than inherited from this shell.

*Filtering stays where it belongs.* Every page renders an already-filtered
snapshot. Nothing here decides visibility, and nothing here can widen it.

One deliberate refusal: a capability that is hidden from this viewer and a
capability that does not exist both produce `404`. Distinguishing them would
publish the existence of something the visibility decision withheld.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from html import escape
from types import MappingProxyType
from typing import Any

from agnara.introspection import (
    AppDescriptor,
    CapabilityDescriptor,
    DiscoveryField,
    DiscoveryVisibility,
    InputDescriptor,
    IntrospectionSnapshot,
    filter_snapshot,
)
from agnara.policy import Principal
from agnara_http._discovery import (
    _CompiledDiscovery,
    _DiscoveryDefinitionError,
    _principal_or_failure,
    _ResolverFailed,
)
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

_HTML_MEDIA_TYPE = b"text/html; charset=utf-8"

#: The first segment of an application's page. A capability id is always one
#: segment and always contains a dot, so the two address spaces cannot collide.
_APP_SEGMENT = "app"

#: The page loads nothing, so nothing needs to be allowed. Every directive here
#: is enforceable precisely because the shell has no script, style, image or
#: font to fetch.
_CONTENT_SECURITY_POLICY = (
    b"default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-security-policy", _CONTENT_SECURITY_POLICY),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
)


@dataclass(frozen=True, slots=True)
class _ExplorerRoute:
    """One declared Explorer, sharing the discovery endpoint's authorization.

    The snapshot, the visibility decision and the principal resolver are the
    same three things the machine-readable endpoint takes, because a human and
    a program looking at one application must not see different applications.
    """

    base_path: str
    snapshot: IntrospectionSnapshot
    visibility: DiscoveryVisibility
    principals: Callable[[_Scope], Principal | None]
    challenge: str | None = None
    allow_anonymous: bool = False
    cache_control: str = "private, no-store"

    def __post_init__(self) -> None:
        if not isinstance(self.base_path, str) or not self.base_path.startswith("/"):
            raise _DiscoveryDefinitionError("explorer base_path must be an absolute path")
        if self.base_path.endswith("/") and self.base_path != "/":
            raise _DiscoveryDefinitionError(
                f"explorer base_path must not end with '/': {self.base_path!r}"
            )
        try:
            segments, parameters = _parse_template(self.base_path)
        except (TypeError, ValueError) as error:
            raise _DiscoveryDefinitionError(str(error)) from error
        if parameters or any(segment is None for segment in segments):
            raise _DiscoveryDefinitionError(
                f"explorer base_path must be static, got {self.base_path!r}"
            )


@dataclass(frozen=True, slots=True)
class _CompiledExplorer:
    """An Explorer whose subtree and headers are fixed at startup."""

    base_path: str
    prefix: str
    discovery: _CompiledDiscovery
    headers: tuple[tuple[bytes, bytes], ...]


def _compile_explorer(
    route: _ExplorerRoute,
    capability_routes: _FrozenRouteRegistry[_CompiledExposure],
) -> _CompiledExplorer:
    """Validate the Explorer and reserve its whole subtree, not just its root.

    A capability route anywhere under the base path would be shadowed, so the
    conflict check covers the subtree rather than the single index path.
    """
    if not isinstance(route, _ExplorerRoute):
        raise _DiscoveryDefinitionError(
            f"explorer route must be an _ExplorerRoute, got {type(route).__name__}"
        )
    if not isinstance(capability_routes, _FrozenRouteRegistry):
        raise TypeError(
            f"capability_routes must be a frozen registry, got {type(capability_routes).__name__}"
        )
    prefix = f"{route.base_path}/"
    for existing in sorted(capability_routes, key=lambda item: (item.method, item.path_template)):
        template = existing.path_template
        if template == route.base_path or template.startswith(prefix):
            raise _DiscoveryDefinitionError(
                f"explorer at {route.base_path!r} would shadow capability route "
                f"{existing.method} {template!r}"
            )

    from agnara_http._discovery import _compile_discovery, _DiscoveryRoute

    discovery = _compile_discovery(
        _DiscoveryRoute(
            path=route.base_path,
            snapshot=route.snapshot,
            visibility=route.visibility,
            principals=route.principals,
            challenge=route.challenge,
            allow_anonymous=route.allow_anonymous,
            cache_control=route.cache_control,
        ),
        capability_routes,
    )
    return _CompiledExplorer(
        base_path=route.base_path,
        prefix=prefix,
        discovery=discovery,
        headers=(*discovery.headers, *_SECURITY_HEADERS),
    )


# --- rendering -------------------------------------------------------------


def _link(href: str, text: str) -> str:
    return f'<a href="{escape(href, quote=True)}">{escape(text)}</a>'


def _document(title: str, body: Iterable[str]) -> bytes:
    """Assemble one page. Every interpolated value is escaped by its producer."""
    head = (
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="robots" content="noindex, nofollow">',
        f"<title>{escape(title)}</title>",
        "</head>",
        "<body>",
        "<main>",
    )
    return "\n".join((*head, *body, "</main>", "</body>", "</html>", "")).encode("utf-8")


def _withheld(visibility: DiscoveryVisibility) -> list[str]:
    """Say what was not published, so absence is legible as withholding."""
    names = sorted(field.value for field in DiscoveryField if not visibility.publishes(field))
    if not names:
        return []
    return [
        "<p><strong>Partial view.</strong> The following was not published to you "
        f"and is absent rather than empty: {escape(', '.join(names))}.</p>"
    ]


def _not_authorization() -> list[str]:
    return [
        "<p>Seeing a capability here is not permission to invoke it. Every "
        "invocation is authorized independently at call time.</p>"
    ]


def _capability_summary(base_path: str, capability: CapabilityDescriptor) -> str:
    transports = f" — {escape(', '.join(capability.transports))}" if capability.transports else ""
    link = _link(f"{base_path}/{capability.id}", capability.id)
    description = f"<br>{escape(capability.description)}" if capability.description else ""
    return f"<li>{link}{transports}{description}</li>"


def _app_path(base_path: str, name: str) -> str:
    """The application's own page.

    Two segments, so it can never be mistaken for a capability id, which is
    always one. That keeps both addressable without either escaping into the
    other's namespace.
    """
    return f"{base_path}/{_APP_SEGMENT}/{name}"


def _app_section(base_path: str, app: AppDescriptor) -> Iterable[str]:
    heading = _link(_app_path(base_path, app.name), f"Application {app.name}")
    yield f"<h2>{heading}</h2>"
    transports = ", ".join(app.transports) if app.transports else "none published"
    yield f"<p>Transports: {escape(transports)}</p>"
    yield "<ul>"
    for capability in app.capabilities:
        yield _capability_summary(base_path, capability)
    yield "</ul>"


def _render_index(
    base_path: str,
    snapshot: IntrospectionSnapshot,
    visibility: DiscoveryVisibility,
) -> bytes:
    title = "Agnara Explorer"
    body: list[str] = [f"<h1>{escape(title)}</h1>"]
    provenance = f"{snapshot.format} version {snapshot.version}"
    if snapshot.project:
        provenance = f"{provenance} — project {snapshot.project}"
    body.append(f"<p>{escape(provenance)}</p>")
    body.extend(_not_authorization())
    body.extend(_withheld(visibility))
    transports = ", ".join(snapshot.transports) if snapshot.transports else "none published"
    body.append(f"<p>Transport availability: {escape(transports)}</p>")
    if not snapshot.apps:
        body.append("<p>No capabilities are visible to you.</p>")
        return _document(title, body)
    for app in snapshot.apps:
        body.extend(_app_section(base_path, app))
    return _document(title, body)


def _definition(term: str, description: str) -> str:
    return f"<dt>{escape(term)}</dt><dd>{escape(description)}</dd>"


def _capability_body(
    base_path: str,
    app: AppDescriptor,
    capability: CapabilityDescriptor,
    visibility: DiscoveryVisibility,
) -> list[str]:
    body: list[str] = [f"<h1>{escape(capability.id)}</h1>"]
    owner = _link(_app_path(base_path, app.name), f"Application {app.name}")
    body.append(f"<p>{_link(base_path, 'Back to the index')} · {owner}</p>")
    if capability.description:
        body.append(f"<p>{escape(capability.description)}</p>")
    body.extend(_not_authorization())
    body.extend(_withheld(visibility))

    body.append("<h2>Facts</h2>")
    body.append("<dl>")
    if visibility.publishes(DiscoveryField.SAFETY):
        body.append(_definition("Risk", capability.risk))
        body.append(_definition("Confirmation", capability.confirmation))
        body.append(_definition("Idempotency", capability.idempotency))
    if capability.effects:
        body.append(_definition("Effects", ", ".join(capability.effects)))
    if capability.scopes:
        body.append(_definition("Required scopes", ", ".join(capability.scopes)))
    body.append(
        _definition(
            "Transports",
            ", ".join(capability.transports) if capability.transports else "none published",
        )
    )
    body.append("</dl>")

    if capability.inputs:
        body.append("<h2>Inputs</h2>")
        body.append("<ul>")
        for item in capability.inputs:
            body.extend(_input_view(item))
        body.append("</ul>")
    elif visibility.publishes(DiscoveryField.INPUTS):
        body.append("<h2>Inputs</h2><p>This capability takes no inputs.</p>")

    if capability.exposures:
        body.append("<h2>Exposures</h2>")
        body.append("<ul>")
        for exposure in capability.exposures:
            body.append(f"<li>{escape(exposure.transport)}: {escape(exposure.name)}</li>")
        body.append("</ul>")

    if capability.dependencies:
        body.append("<h2>Dependencies</h2>")
        body.append("<ul>")
        for dependency in capability.dependencies:
            body.append(f"<li>{escape(dependency.parameter)}: {escape(dependency.type.name)}</li>")
        body.append("</ul>")

    if capability.policies:
        body.append("<h2>Policies</h2>")
        body.append("<ul>")
        for policy in capability.policies:
            body.append(f"<li>{escape(policy.kind)}</li>")
        body.append("</ul>")
    return body


_MAX_SCHEMA_DEPTH = 16


def _scalar(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _schema_rows(fragment: object, depth: int = 0) -> Iterable[str]:
    """Render a JSON Schema fragment as nested structure rather than a blob.

    A reader wants an input's shape, and escaped JSON on one line is not that.
    Depth is bounded because this walks data an application produced; the
    snapshot already refuses anything deeper than 64 levels, so reaching this
    bound means a legitimately deep schema whose tail is better summarized
    than unrolled.
    """
    if depth > _MAX_SCHEMA_DEPTH:
        yield "<li>(nested further)</li>"
        return
    if isinstance(fragment, Mapping):
        entries: Iterable[tuple[object, object]] = sorted(
            fragment.items(), key=lambda item: str(item[0])
        )
    elif isinstance(fragment, list):
        entries = enumerate(fragment)
    else:
        yield f"<li>{escape(_scalar(fragment))}</li>"
        return
    for key, value in entries:
        label = escape(str(key))
        if isinstance(value, Mapping | list):
            yield f"<li>{label}:<ul>"
            yield from _schema_rows(value, depth + 1)
            yield "</ul></li>"
        else:
            yield f"<li>{label}: {escape(_scalar(value))}</li>"


def _input_view(item: InputDescriptor) -> Iterable[str]:
    """One input: its name, whether it is required, and its published schema."""
    requirement = "required" if item.required else "optional"
    yield f"<li>{escape(item.name)} ({escape(requirement)})"
    try:
        fragment = json.loads(item.schema)
    except json.JSONDecodeError:  # pragma: no cover - descriptors validate this
        fragment = {}
    yield "<ul>"
    yield from _schema_rows(fragment)
    yield "</ul></li>"


def _render_app(
    base_path: str,
    snapshot: IntrospectionSnapshot,
    visibility: DiscoveryVisibility,
    name: str,
) -> bytes | None:
    """Render one application, or ``None`` when this viewer has no such page."""
    for app in snapshot.apps:
        if app.name != name:
            continue
        title = f"Application {app.name}"
        body: list[str] = [f"<h1>{escape(title)}</h1>"]
        body.append(f"<p>{_link(base_path, 'Back to the index')}</p>")
        body.extend(_not_authorization())
        body.extend(_withheld(visibility))
        transports = ", ".join(app.transports) if app.transports else "none published"
        body.append(f"<p>Transports: {escape(transports)}</p>")

        body.append("<h2>Capabilities</h2>")
        body.append("<ul>")
        for capability in app.capabilities:
            body.append(_capability_summary(base_path, capability))
        body.append("</ul>")

        if app.providers:
            body.append("<h2>Providers</h2>")
            body.append("<ul>")
            for provider in app.providers:
                requires = ", ".join(item.name for item in provider.requires)
                suffix = f" requires {requires}" if requires else ""
                body.append(
                    f"<li>{escape(provider.provides.name)}: "
                    f"{escape(provider.scope)} {escape(provider.kind)}{escape(suffix)}</li>"
                )
            body.append("</ul>")
        elif visibility.publishes(DiscoveryField.PROVIDERS):
            body.append("<h2>Providers</h2><p>This application binds no providers.</p>")
        return _document(title, body)
    return None


def _render_capability(
    base_path: str,
    snapshot: IntrospectionSnapshot,
    visibility: DiscoveryVisibility,
    capability_id: str,
) -> bytes | None:
    """Render one capability, or ``None`` when this viewer has no such page."""
    for app in snapshot.apps:
        for capability in app.capabilities:
            if capability.id == capability_id:
                return _document(
                    capability.id,
                    _capability_body(base_path, app, capability, visibility),
                )
    return None


# --- serving ---------------------------------------------------------------


class _ExplorerDispatcher:
    """Serve the Explorer subtree, delegating every other path unchanged."""

    __slots__ = ("_explorer", "_fallback", "_problem_types")

    def __init__(
        self,
        explorer: _CompiledExplorer,
        fallback: _HTTPDispatch,
        *,
        problem_types: Mapping[str, str] = _ABOUT_BLANK_TYPES,
    ) -> None:
        if not isinstance(explorer, _CompiledExplorer):
            raise TypeError(f"explorer must be compiled, got {type(explorer).__name__}")
        if not callable(fallback):
            raise TypeError(f"fallback must be callable, got {type(fallback).__name__}")
        if not isinstance(problem_types, Mapping):
            raise TypeError("problem_types must be a mapping")
        self._explorer = explorer
        self._fallback = fallback
        self._problem_types = MappingProxyType(dict(problem_types))

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        method = scope.get("method")
        if not isinstance(method, str):
            raise TypeError("ASGI scope 'method' must be a string")
        path = _routed_path(scope)
        base = self._explorer.base_path
        if path != base and not path.startswith(self._explorer.prefix):
            await self._fallback(scope, receive, send)
            return

        normalized = _normalize_method(method)
        head = normalized == "HEAD"
        if normalized not in {"GET", "HEAD"}:
            await self._send_error(self._method_not_allowed(path), send)
            return

        principal = _principal_or_failure(self._explorer.discovery, scope)
        if isinstance(principal, _ResolverFailed):
            await self._send_error(_INTERNAL_PROBLEM, send, head=head)
            return
        if principal is None:
            await self._send_error(self._unauthenticated(path), send, head=head)
            return

        document = filter_snapshot(
            self._explorer.discovery.snapshot,
            self._explorer.discovery.visibility,
            principal,
        )
        if path == base:
            body = _render_index(base, document, self._explorer.discovery.visibility)
        else:
            body = self._subpage(base, document, path)
        if body is None:
            # Hidden and absent are the same answer on purpose: telling them
            # apart would publish the existence of something withheld.
            await self._send_error(self._not_found(path), send, head=head)
            return
        await _send_response(self._page(body), send, head=head)

    async def _send_error(
        self, response: _SerializedResponse, send: _Send, *, head: bool = False
    ) -> None:
        """Never cache a viewer-dependent denial, missing target or resolver failure.

        Preserve the canonical problem and challenge/Allow headers, without
        mutating the shared internal-error response. Errors always use no-store
        even when the composer selected a private cache lifetime for HTML.
        """
        headers = dict(response.headers)
        headers.update(self._explorer.headers)
        headers[b"cache-control"] = b"private, no-store"
        await _send_response(
            _SerializedResponse(response.status, tuple(headers.items()), response.body),
            send,
            head=head,
        )

    def _subpage(
        self,
        base: str,
        document: IntrospectionSnapshot,
        path: str,
    ) -> bytes | None:
        """Resolve one page under the base path, or nothing this viewer may see.

        One segment is a capability id; two segments beginning with the
        application marker are an application. Anything else has no page,
        which is the same answer as a capability withheld from this viewer.
        """
        visibility = self._explorer.discovery.visibility
        segments = path[len(self._explorer.prefix) :].split("/")
        if len(segments) == 1 and segments[0]:
            return _render_capability(base, document, visibility, segments[0])
        if len(segments) == 2 and segments[0] == _APP_SEGMENT and segments[1]:
            return _render_app(base, document, visibility, segments[1])
        return None

    def _page(self, body: bytes) -> _SerializedResponse:
        return _SerializedResponse(
            200,
            (
                (b"content-type", _HTML_MEDIA_TYPE),
                (b"content-length", str(len(body)).encode("ascii")),
                *self._explorer.headers,
            ),
            body,
        )

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
            "the explorer requires an identified viewer",
            headers=self._explorer.discovery.challenge_headers,
            problem_types=self._problem_types,
            instance=_problem_instance(path),
        )

    def _not_found(self, path: str) -> _SerializedResponse:
        return _serialize_transport_failure(
            _TransportFailure.NOT_FOUND,
            "no capability is visible at this target",
            problem_types=self._problem_types,
            instance=_problem_instance(path),
        )
