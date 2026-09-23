"""The supported way to expose Agnara capabilities over HTTP.

This is the whole public surface of ``agnara-http``. Everything else in the
package is an underscore-prefixed implementation detail, and the point of this
module is that an application never has to reach for one.

Fourteen names, because the package exported nothing until the exposure model
beneath it was settled (ADR 0070) and a governed contract is easier to keep
than an accidental wide one:

``Http``
    Declare which capabilities one named HTTP surface exposes, and compile it.
``HttpApplication``
    The compiled result: an immutable ASGI 3 application.
``Binding`` / ``BindingSource``
    Where one capability input is read from in a request. Explicit by
    decision, not by omission — ADR 0026.
``OpenApiInfo`` / ``OpenApiOperation``
    Document metadata, and the per-operation decision to publish at all.
``HttpDefinitionError``
    One composition mistake, raised at startup.
``HttpDocumentation`` / ``OpenApiSchema`` / ``SwaggerUI`` / ``Scalar`` /
``ReDoc`` / ``DocumentationAssets`` / ``HttpExplorer``
    Explicit, independent documentation and Explorer composition selections.

A worked example lives in ``docs/HTTP_COMPOSITION.md``; the short version::

    app = Agnara("billing")


    @app.capability
    def refund(payment_id: str) -> str: ...


    http = Http()
    http.post("/refunds", refund, Binding("payment_id", BindingSource.QUERY))
    asgi = http.compile(app.compile(), openapi=OpenApiInfo("Billing", "1.0"))

The fourteen values re-exported by ``agnara_http`` are stable syntax governed
by ``docs/public-api.json``. This module itself is intentionally not a second
public import path; applications import the values from ``agnara_http``.

The public value types are translated into the adapter's internal ones rather
than aliasing them. That is deliberate: it is what lets routing, binding and
projection change shape without breaking an application, which is the reason
this package declared no public surface for three releases.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from agnara import CapabilityDefinition, DefinitionError, FrozenCapabilityRegistry
from agnara.capability import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import ExecutionPlan, TelemetryHook
from agnara.exposure import SurfaceCompilation, SurfaceId
from agnara.introspection import DiscoveryVisibility, IntrospectionSnapshot
from agnara.policy import ConfirmationVerifier, Principal
from agnara.schema import SchemaAdapter
from agnara_http._asgi import _ASGIBoundary
from agnara_http._binding import _BindingDefinitionError, _BindingSource, _InputBinding
from agnara_http._dispatch import (
    _CompiledExposure,
    _DispatchOptions,
    _HTTPDispatcher,
    _HTTPExposure,
    _OpenAPIPublication,
    _problem_instance,
    _routed_path,
)
from agnara_http._documentation import (
    _documentation_security_headers,
    _DocumentationDefinitionError,
    _DocumentationPage,
    _DocumentationRegistry,
    _DocumentationRequest,
    _DocumentationUnavailable,
    _https_origin,
)
from agnara_http._explorer import _compile_explorer, _ExplorerDispatcher, _ExplorerRoute
from agnara_http._exposures import DEFAULT_SURFACE, _compile_exposure_surface
from agnara_http._lifespan import _LifespanDispatcher
from agnara_http._openapi import _OpenAPIDefinitionError, _OpenAPIInfo, _project_openapi
from agnara_http._problem import (
    _allow_header,
    _compile_problem_types,
    _ProblemDefinitionError,
    _serialize_transport_failure,
    _TransportFailure,
)
from agnara_http._redoc import _ReDocProvider
from agnara_http._response import _send_response, _SerializedResponse
from agnara_http._routing import (
    _FrozenRouteRegistry,
    _request_method,
    _RouteDefinitionError,
    _RouteRegistryFrozenError,
)
from agnara_http._scalar import _ScalarProvider
from agnara_http._sse import _SSEDefinitionError, _SSEProjection
from agnara_http._surfaces import (
    _compile_surfaces,
    _HTTPSurface,
    _SurfaceDefinitionError,
    _SurfaceDispatcher,
)
from agnara_http._swagger import _SwaggerUIProvider

__all__: list[str] = []

#: Adapter-internal failures translated into `HttpDefinitionError`.
#:
#: A public API should not hand back `_BindingDefinitionError` or
#: `_RouteRegistryFrozenError`: an application would end up naming a private
#: type in an `except` clause, which is the coupling this module exists to
#: remove. The original stays on `__cause__`, so nothing is hidden from
#: whoever is debugging.
_TRANSLATED: tuple[type[Exception], ...] = (
    _BindingDefinitionError,
    _DocumentationDefinitionError,
    _DocumentationUnavailable,
    _OpenAPIDefinitionError,
    _ProblemDefinitionError,
    _RouteDefinitionError,
    _RouteRegistryFrozenError,
    _SSEDefinitionError,
    _SurfaceDefinitionError,
)

#: One lifespan cycle, supplied by the application. Called once per cycle.
type Lifecycle = Callable[[], AbstractAsyncContextManager[None]]


@asynccontextmanager
async def _owned_lifecycle(
    container: DIContainer, lifecycle: Lifecycle | None
) -> AsyncIterator[None]:
    """Close HTTP-owned providers before releasing application-owned resources."""
    async with AsyncExitStack() as stack:
        if lifecycle is not None:
            entered = await stack.enter_async_context(lifecycle())
            if entered is not None:
                raise TypeError("lifecycle context must yield None")
        stack.push_async_callback(container.aclose)
        yield


#: What a route method accepts for the capability it exposes.
type CapabilityRef = CapabilityDefinition | Callable[..., Any]

type _Scope = dict[str, Any]
type _Routes = _FrozenRouteRegistry[_CompiledExposure]


class HttpDefinitionError(DefinitionError):
    """One HTTP composition is invalid, ambiguous or too late.

    Covers a duplicate route, an input with no binding or an unsupported one,
    a declaration added after compilation, and an application that cannot be
    projected into OpenAPI truthfully.

    One class rather than a taxonomy, matching `McpToolDefinitionError` in the
    sibling adapter. All of these abort startup, and nothing catches them
    selectively in production; the message names the specific problem and
    `__cause__` keeps the adapter's own diagnostic. A finer hierarchy is a
    change this alpha should not promise before an application asks for one.

    A `DefinitionError`, so `except AgnaraError` already covers it and an
    application need not learn a second error root (ADR 0005).
    """


class BindingSource(StrEnum):
    """Where in a request one capability input is read from.

    ``BODY``, ``FORM`` and ``UPLOAD`` each read the request body, so a route
    combining a JSON body with either of the others is refused: one request
    has one body and the adapter will not guess which encoding was meant
    (ADR 0072).

    ``FORM`` and ``UPLOAD`` may be combined freely, which is what an ordinary
    upload form posts: some text fields and a file.
    """

    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    BODY = "body"
    #: One RFC 6265 cookie, read by name. Case-sensitive, unlike a header.
    COOKIE = "cookie"
    #: One form field, from either an URL-encoded or a multipart body. An
    #: application asks for a field, not for an encoding.
    FORM = "form"
    #: One uploaded file part, as ``bytes``. The input must be annotated
    #: ``bytes``; the client filename is deliberately not exposed.
    UPLOAD = "upload"


_SOURCES: dict[BindingSource, _BindingSource] = {
    BindingSource.PATH: _BindingSource.PATH,
    BindingSource.QUERY: _BindingSource.QUERY,
    BindingSource.HEADER: _BindingSource.HEADER,
    BindingSource.BODY: _BindingSource.BODY,
    BindingSource.COOKIE: _BindingSource.COOKIE,
    BindingSource.FORM: _BindingSource.FORM,
    BindingSource.UPLOAD: _BindingSource.UPLOAD,
}


class Binding:
    """Read one capability input from one place in the request.

    ``wire_name`` renames the input on the wire, so a capability parameter
    named ``account_id`` can arrive as the ``X-Account-Id`` header without the
    capability knowing that HTTP exists.

    Binding is explicit by decision (ADR 0026). A path parameter is *not*
    inferred from the template: an application that renames a capability
    parameter should get a startup failure rather than a silently unbound
    input that becomes a validation error on the first request.
    """

    __slots__ = ("_input_name", "_source", "_wire_name")

    def __init__(
        self,
        input_name: str,
        source: BindingSource,
        *,
        wire_name: str | None = None,
    ) -> None:
        if not isinstance(input_name, str) or not input_name:
            raise HttpDefinitionError("binding input_name must be a non-empty string")
        if not isinstance(source, BindingSource):
            raise HttpDefinitionError(
                f"binding source must be a BindingSource, got {type(source).__name__}"
            )
        if wire_name is not None and (not isinstance(wire_name, str) or not wire_name):
            raise HttpDefinitionError("binding wire_name must be a non-empty string or None")
        self._input_name = input_name
        self._source = source
        self._wire_name = wire_name

    @property
    def input_name(self) -> str:
        """The capability input this binding fills."""
        return self._input_name

    @property
    def source(self) -> BindingSource:
        """Where the value is read from."""
        return self._source

    @property
    def wire_name(self) -> str | None:
        """The name on the wire, when it differs from the input name."""
        return self._wire_name

    def _internal(self) -> _InputBinding:
        return _InputBinding(self._input_name, _SOURCES[self._source], self._wire_name)

    def __repr__(self) -> str:
        wire = "" if self._wire_name is None else f", wire_name={self._wire_name!r}"
        return f"Binding({self._input_name!r}, {self._source.name}{wire})"


class OpenApiInfo:
    """Required OpenAPI document metadata.

    Kept separate from capability semantics: a title and a version describe the
    document a deployment publishes, not what any capability means.
    """

    __slots__ = ("_description", "_summary", "_title", "_version")

    def __init__(
        self,
        title: str,
        version: str,
        *,
        summary: str | None = None,
        description: str | None = None,
    ) -> None:
        self._title = title
        self._version = version
        self._summary = summary
        self._description = description
        # Validate through the adapter's own type so one rule set applies.
        self._internal()

    def _internal(self) -> _OpenAPIInfo:
        try:
            return _OpenAPIInfo(self._title, self._version, self._summary, self._description)
        except _OpenAPIDefinitionError as error:
            raise HttpDefinitionError(str(error)) from error

    @property
    def title(self) -> str:
        return self._title

    @property
    def version(self) -> str:
        return self._version

    @property
    def summary(self) -> str | None:
        return self._summary

    @property
    def description(self) -> str | None:
        return self._description

    def __repr__(self) -> str:
        return f"OpenApiInfo({self._title!r}, {self._version!r})"


class OpenApiOperation:
    """Publish one exposure in the OpenAPI document, with this metadata.

    Presence is the decision. An exposure without one is served and stays out
    of the document entirely — no path, no identifier, no description, no tag,
    no schema fragment (ADR 0035). That is why publication is opt-in rather
    than a flag with a default: a deployment that has not thought about what it
    publishes publishes nothing.

    ``publish_description`` is separate from ``summary`` because a capability
    docstring is written for developers reading the code and may say more than
    a public document should.
    """

    __slots__ = ("_deprecated", "_publish_description", "_summary", "_tags")

    def __init__(
        self,
        *,
        summary: str | None = None,
        publish_description: bool = False,
        tags: Sequence[str] = (),
        deprecated: bool = False,
    ) -> None:
        self._summary = summary
        self._publish_description = publish_description
        self._tags = tuple(tags)
        self._deprecated = deprecated
        self._internal()

    def _internal(self) -> _OpenAPIPublication:
        try:
            return _OpenAPIPublication(
                self._summary,
                self._publish_description,
                self._tags,
                self._deprecated,
            )
        except _BindingDefinitionError as error:
            raise HttpDefinitionError(str(error)) from error

    @property
    def summary(self) -> str | None:
        return self._summary

    @property
    def publish_description(self) -> bool:
        return self._publish_description

    @property
    def tags(self) -> tuple[str, ...]:
        return self._tags

    @property
    def deprecated(self) -> bool:
        return self._deprecated

    def __repr__(self) -> str:
        return f"OpenApiOperation(summary={self._summary!r}, tags={self._tags!r})"


@dataclass(frozen=True, slots=True)
class DocumentationAssets:
    """Choose verified local assets or explicitly allow pinned CDN origins.

    ``local()`` is the default and has no runtime network dependency.
    ``remote(...)`` does not accept arbitrary URLs: built-in providers keep
    their own exact-version URL and SRI evidence, while this value grants only
    the exact HTTPS origins a deployment accepts.
    """

    allowed_remote_origins: frozenset[str] = frozenset()
    remote_assets: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_remote_origins, frozenset):
            raise HttpDefinitionError("allowed_remote_origins must be a frozenset of HTTPS origins")
        if not isinstance(self.remote_assets, bool):
            raise HttpDefinitionError("remote_assets must be a boolean")
        if self.remote_assets and not self.allowed_remote_origins:
            raise HttpDefinitionError(
                "remote documentation assets need at least one allowed HTTPS origin"
            )
        for origin in self.allowed_remote_origins:
            try:
                _https_origin(origin, label="allowed remote origin")
            except _DocumentationDefinitionError as error:
                raise HttpDefinitionError(str(error)) from error

    @classmethod
    def local(cls) -> Self:
        """Use the package's hash-verified, same-origin assets."""
        return cls()

    @classmethod
    def remote(cls, *origins: str) -> Self:
        """Allow built-in CDN assets only from these exact HTTPS origins."""
        return cls(frozenset(origins), remote_assets=True)


@dataclass(frozen=True, slots=True)
class OpenApiSchema:
    """Publish the generated OpenAPI JSON at one explicit static path."""

    path: str = "/openapi.json"


@dataclass(frozen=True, slots=True)
class SwaggerUI:
    """Configure the built-in Swagger UI documentation page."""

    path: str = "/docs"
    try_it: bool = False
    assets: DocumentationAssets = field(default_factory=DocumentationAssets.local)


@dataclass(frozen=True, slots=True)
class Scalar:
    """Configure the built-in Scalar documentation page."""

    path: str = "/scalar"
    try_it: bool = False
    assets: DocumentationAssets = field(default_factory=DocumentationAssets.local)


@dataclass(frozen=True, slots=True)
class ReDoc:
    """Configure the built-in read-only ReDoc documentation page.

    The bundled ReDoc release currently declares OpenAPI 3.1 support only.
    Selecting it for Agnara's canonical 3.2 document therefore fails during
    compilation with a diagnostic rather than receiving a rewritten schema.
    """

    path: str = "/redoc"
    assets: DocumentationAssets = field(default_factory=DocumentationAssets.local)


@dataclass(frozen=True, slots=True)
class HttpDocumentation:
    """Independently select OpenAPI publication and built-in browser UIs.

    ``HttpDocumentation()`` is the local development profile: it publishes
    ``/openapi.json`` and serves Swagger UI at ``/docs``. Passing ``None``
    for an individual selection disables only that surface. A UI still works
    when ``schema=None`` because it receives the generated document directly.
    """

    schema: OpenApiSchema | None = field(default_factory=OpenApiSchema)
    swagger: SwaggerUI | None = field(default_factory=SwaggerUI)
    scalar: Scalar | None = None
    redoc: ReDoc | None = None

    def __post_init__(self) -> None:
        selections = (
            ("schema", self.schema, OpenApiSchema),
            ("swagger", self.swagger, SwaggerUI),
            ("scalar", self.scalar, Scalar),
            ("redoc", self.redoc, ReDoc),
        )
        for name, value, expected in selections:
            if value is not None and not isinstance(value, expected):
                raise HttpDefinitionError(
                    f"documentation {name} must be a {expected.__name__} or None"
                )


@dataclass(frozen=True, slots=True)
class HttpExplorer:
    """Publish the read-only Explorer from an authorized filtered snapshot.

    Explorer is deliberately separate from OpenAPI documentation. The caller
    supplies the protocol-neutral snapshot, its visibility policy and the
    application's principal resolver; this adapter never infers identity from
    HTTP headers and viewing never authorizes invocation.
    """

    snapshot: IntrospectionSnapshot
    visibility: DiscoveryVisibility
    principals: Callable[[_Scope], Principal | None]
    path: str = "/agnara"
    challenge: str | None = None
    allow_anonymous: bool = False
    cache_control: str = "private, no-store"

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, IntrospectionSnapshot):
            raise HttpDefinitionError("explorer snapshot must be an IntrospectionSnapshot")
        if not isinstance(self.visibility, DiscoveryVisibility):
            raise HttpDefinitionError("explorer visibility must be a DiscoveryVisibility")
        if not callable(self.principals):
            raise HttpDefinitionError("explorer principals must be callable")
        if not isinstance(self.allow_anonymous, bool):
            raise HttpDefinitionError("explorer allow_anonymous must be a boolean")
        if not self.allow_anonymous and self.challenge is None:
            raise HttpDefinitionError(
                "an authenticated explorer needs a WWW-Authenticate challenge; "
                "set challenge=... or allow_anonymous=True"
            )
        if self.allow_anonymous and self.challenge is not None:
            raise HttpDefinitionError("an anonymous explorer must not declare a challenge")


@dataclass(frozen=True, slots=True)
class _DocumentationRoute:
    """One built-in page, rendered from a fixed generated document."""

    name: str
    path: str
    assets_path: str
    provider: object
    artifact: bytes
    openapi_version: str
    title: str
    schema_path: str | None
    allowed_remote_origins: frozenset[str]
    try_it: bool


class _DocumentationDispatcher:
    """Render documentation pages and root-aware initializer assets on demand.

    The compiled route choices and document bytes are immutable. Rendering at
    request time is intentional: an ASGI mount prefix is request metadata, so
    baking ``/docs`` into the initializer would make a mounted application
    fetch from the host root instead of its own ``root_path``.
    """

    __slots__ = ("_fallback", "_problem_types", "_routes")

    def __init__(
        self,
        routes: tuple[_DocumentationRoute, ...],
        fallback: Callable[[_Scope, Callable[[], Any], Callable[[Any], Any]], Any],
        *,
        problem_types: Mapping[str, str],
    ) -> None:
        self._routes = routes
        self._fallback = fallback
        self._problem_types = dict(problem_types)

    async def __call__(
        self, scope: _Scope, receive: Callable[[], Any], send: Callable[[Any], Any]
    ) -> None:
        method = scope.get("method")
        if not isinstance(method, str):
            raise TypeError("ASGI scope 'method' must be a string")
        path = _routed_path(scope)
        matched = self._match(path)
        if matched is None:
            await self._fallback(scope, receive, send)
            return
        route, asset_name = matched
        request_method = _request_method(method)
        if request_method not in {"GET", "HEAD"}:
            response = _serialize_transport_failure(
                _TransportFailure.METHOD_NOT_ALLOWED,
                "the target does not accept this method",
                headers=_allow_header(("GET", "HEAD")),
                problem_types=self._problem_types,
                instance=_problem_instance(path),
            )
            await _send_response(response, send)
            return
        page = self._render(route, scope)
        if asset_name is None:
            response = _SerializedResponse(
                200,
                (
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", str(len(page.html)).encode("ascii")),
                    *_documentation_security_headers(page.csp),
                ),
                page.html,
            )
        else:
            asset = page.assets.get(asset_name)
            if asset is None:
                await self._fallback(scope, receive, send)
                return
            response = _SerializedResponse(
                200,
                (
                    (b"content-type", asset.media_type.encode("ascii")),
                    (b"content-length", str(len(asset.body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ),
                asset.body,
            )
        await _send_response(response, send, head=request_method == "HEAD")

    def _match(self, path: str) -> tuple[_DocumentationRoute, str | None] | None:
        for route in self._routes:
            if path == route.path:
                return route, None
            prefix = f"{route.assets_path}/"
            if path.startswith(prefix):
                return route, path[len(prefix) :]
        return None

    def _render(self, route: _DocumentationRoute, scope: _Scope) -> _DocumentationPage:
        return _render_documentation_page(route, scope)


def _mounted_path(path: str, scope: _Scope) -> str:
    """Prefix a configured same-origin path with ASGI's trusted mount path."""
    root_path = scope.get("root_path", "")
    if not isinstance(root_path, str):
        raise TypeError("ASGI scope 'root_path' must be a string")
    if not root_path:
        return path
    if not root_path.startswith("/") or root_path.startswith("//"):
        raise TypeError("ASGI scope 'root_path' must be a same-origin absolute path")
    return f"{root_path.rstrip('/')}{path}"


def _render_documentation_page(route: _DocumentationRoute, scope: _Scope) -> _DocumentationPage:
    """Render one validated built-in provider with exactly one schema source."""
    schema_url = None if route.schema_path is None else _mounted_path(route.schema_path, scope)
    request = _DocumentationRequest(
        document_url=schema_url,
        document=None if schema_url is not None else route.artifact,
        title=route.title,
        assets_url=_mounted_path(route.assets_path, scope),
        openapi_version=route.openapi_version,
        try_it=route.try_it,
    )
    registry = _DocumentationRegistry()
    registry.register(route.provider)
    return registry.render(
        route.name,
        request,
        allowed_remote_origins=route.allowed_remote_origins,
    )


def _limits(declaration: _Declaration) -> dict[str, int]:
    """Only the limits this route overrode, so adapter defaults still apply."""
    limits: dict[str, int] = {}
    if declaration.max_body_bytes is not None:
        limits["max_body_bytes"] = declaration.max_body_bytes
    if declaration.max_parts is not None:
        limits["max_parts"] = declaration.max_parts
    return limits


class _Declaration:
    """One recorded route, before any capability or plan is resolved."""

    __slots__ = (
        "bindings",
        "max_body_bytes",
        "max_event_bytes",
        "max_parts",
        "method",
        "openapi",
        "path",
        "sse",
        "target",
    )

    def __init__(
        self,
        method: str,
        path: str,
        target: CapabilityRef,
        bindings: tuple[Binding, ...],
        openapi: OpenApiOperation | None,
        max_body_bytes: int | None,
        max_parts: int | None,
        sse: bool = False,
        max_event_bytes: int | None = None,
    ) -> None:
        self.method = method
        self.path = path
        self.target = target
        self.bindings = bindings
        self.openapi = openapi
        self.max_body_bytes = max_body_bytes
        self.max_parts = max_parts
        self.sse = sse
        self.max_event_bytes = max_event_bytes

    def projection(self) -> _SSEProjection | None:
        """The SSE contract this declaration asked for, if it asked for one."""
        if not self.sse:
            return None
        if self.max_event_bytes is None:
            return _SSEProjection()
        return _SSEProjection(self.max_event_bytes)

    def describe(self) -> str:
        return f"{self.method} {self.path}"


class HttpApplication:
    """One compiled HTTP surface: an immutable ASGI 3 application.

    Call it the way any ASGI server does::

        uvicorn.run(asgi)  # or: hypercorn, granian, daphne

    Being ASGI is a boundary, not an integration. Agnara speaks ASGI 3 and
    nothing here promises support for a specific framework; that is
    `1.0.0` (ADR 0068).

    Compiled routes and plans are immutable. The owned DI container and
    lifespan belong to one application's event loop, not multiple worker loops.
    """

    __slots__ = ("_boundary", "_exposures", "_info", "_plans", "_routes", "_surface")

    def __init__(
        self,
        surface: SurfaceId,
        boundary: _ASGIBoundary,
        routes: _Routes,
        exposures: SurfaceCompilation[Any],
        plans: tuple[ExecutionPlan, ...],
        info: OpenApiInfo | None,
    ) -> None:
        self._surface = surface
        self._boundary = boundary
        self._routes = routes
        self._exposures = exposures
        self._plans = plans
        self._info = info

    async def __call__(
        self,
        scope: _Scope,
        receive: Callable[[], Any],
        send: Callable[[Any], Any],
    ) -> None:
        """Serve one ASGI connection: an ``http`` scope, or ``lifespan``.

        Lifespan shutdown closes the surface's singleton dependency resources,
        even when no application lifecycle callback was configured.
        """
        await self._boundary(scope, receive, send)

    @property
    def surface(self) -> SurfaceId:
        """This surface's identity in the project-wide exposure registry."""
        return self._surface

    @property
    def exposures(self) -> SurfaceCompilation[Any]:
        """The neutral exposure records, for `agnara.exposure.compile_exposures`.

        Pass this to the project aggregation step to get one frozen answer to
        where each capability is reachable, across HTTP, MCP and any later
        adapter. The ``runtime`` member carries this adapter's own compiled
        route table; it is adapter-owned and not part of the public contract.
        """
        return self._exposures

    @property
    def plans(self) -> tuple[ExecutionPlan, ...]:
        """The compiled execution plans, in declaration order.

        `agnara.introspection.describe_app` needs these, so an application
        that wants a snapshot does not have to compile plans a second time.
        """
        return self._plans

    def openapi(self) -> dict[str, Any]:
        """Project the compiled surface into an OpenAPI 3.2 document.

        Deterministic: the same compiled application yields the same document,
        which is what makes it reviewable in version control.

        Only exposures declared with an `OpenApiOperation` appear.

        Raises:
            HttpDefinitionError: no `OpenApiInfo` was supplied at compilation,
                so there is no document metadata to project with.
        """
        if self._info is None:
            raise HttpDefinitionError(
                "this application was compiled without OpenApiInfo, so it has no "
                "OpenAPI document; pass openapi=OpenApiInfo(title, version) to compile()"
            )
        try:
            return _project_openapi(self._routes, self._info._internal())
        except _TRANSLATED as error:
            raise HttpDefinitionError(str(error)) from error

    def __repr__(self) -> str:
        return f"HttpApplication({str(self._surface)!r}, {len(self._routes)} routes)"


class Http:
    """Declare and compile one named HTTP surface.

    ``surface`` names this deployment inside the project, so one project may
    run a public API and an admin API whose routes never collide::

        public = Http("public")
        admin = Http("admin")

    Declaration belongs here rather than on the capability or the app: a
    capability says what an operation means, an `App` says which bounded
    context owns it, and the composition root says which surfaces expose it
    (ADR 0070). That is what keeps the same app usable in a worker, a public
    service and an agent-facing service.

    The builder is single-use. `compile` closes it, and a later declaration
    fails rather than being silently dropped after the routes were frozen
    (ADR 0005).
    """

    __slots__ = ("_declarations", "_frozen", "_surface")

    def __init__(self, surface: str = DEFAULT_SURFACE) -> None:
        self._surface = self._identity(surface)
        self._declarations: list[_Declaration] = []
        self._frozen = False

    @staticmethod
    def _identity(surface: str) -> SurfaceId:
        try:
            return SurfaceId("http", surface)
        except DefinitionError as error:
            raise HttpDefinitionError(str(error)) from error

    @property
    def surface(self) -> SurfaceId:
        """This surface's identity in the project-wide exposure registry."""
        return self._surface

    @property
    def is_compiled(self) -> bool:
        """Whether `compile` has closed declaration."""
        return self._frozen

    def route(
        self,
        method: str,
        path: str,
        capability: CapabilityRef,
        *bindings: Binding,
        openapi: OpenApiOperation | None = None,
        max_body_bytes: int | None = None,
        max_parts: int | None = None,
    ) -> Self:
        """Expose one capability at one method and path.

        Use this for a method with no named helper below — ``OPTIONS``,
        ``HEAD``, ``TRACE``, ``QUERY``. The named helpers exist because they
        are the ones an application reaches for constantly.

        Args:
            method: the HTTP method. Case-insensitive.
            path: a route template such as ``/orders/{order_id}``.
            capability: a capability declared on the application, either the
                decorated function or its `CapabilityDefinition`.
            bindings: one `Binding` per input the request supplies.
            openapi: supply an `OpenApiOperation` to publish this operation in
                the OpenAPI document. Omit it and the operation is served but
                not documented.
            max_body_bytes: override the request body limit for this route.
            max_parts: override how many parts a multipart body may carry.
                Total size is already bounded by ``max_body_bytes``; this
                bounds the count, because a small body can still hold many
                empty parts.

        Returns:
            This builder, so declarations can be chained.

        Raises:
            HttpDefinitionError: the builder has already compiled, or an
                argument is not of the expected type. Route grammar,
                collisions and binding validity are checked at `compile`,
                because that is when the whole surface is known.
        """
        if self._frozen:
            raise HttpDefinitionError(
                f"cannot declare {method} {path} after {str(self._surface)!r} compiled; "
                "HTTP routes are frozen at startup compilation (ADR 0005)"
            )
        if not isinstance(method, str) or not method:
            raise HttpDefinitionError("route method must be a non-empty string")
        if not isinstance(path, str) or not path:
            raise HttpDefinitionError("route path must be a non-empty string")
        for index, binding in enumerate(bindings):
            if not isinstance(binding, Binding):
                raise HttpDefinitionError(
                    f"{method} {path}: binding {index} must be a Binding, got "
                    f"{type(binding).__name__}"
                )
        if openapi is not None and not isinstance(openapi, OpenApiOperation):
            raise HttpDefinitionError(
                f"{method} {path}: openapi must be an OpenApiOperation or None, got "
                f"{type(openapi).__name__}"
            )
        for name, limit in (("max_body_bytes", max_body_bytes), ("max_parts", max_parts)):
            if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)):
                raise HttpDefinitionError(f"{method} {path}: {name} must be an integer or None")
        self._declarations.append(
            _Declaration(
                method.upper(),
                path,
                capability,
                bindings,
                openapi,
                max_body_bytes,
                max_parts,
            )
        )
        return self

    def get(
        self,
        path: str,
        capability: CapabilityRef,
        *bindings: Binding,
        openapi: OpenApiOperation | None = None,
    ) -> Self:
        """Expose a capability at ``GET path``. ``HEAD`` follows from it."""
        return self.route("GET", path, capability, *bindings, openapi=openapi)

    def post(
        self,
        path: str,
        capability: CapabilityRef,
        *bindings: Binding,
        openapi: OpenApiOperation | None = None,
        max_body_bytes: int | None = None,
        max_parts: int | None = None,
    ) -> Self:
        """Expose a capability at ``POST path``."""
        return self.route(
            "POST",
            path,
            capability,
            *bindings,
            openapi=openapi,
            max_body_bytes=max_body_bytes,
            max_parts=max_parts,
        )

    def put(
        self,
        path: str,
        capability: CapabilityRef,
        *bindings: Binding,
        openapi: OpenApiOperation | None = None,
        max_body_bytes: int | None = None,
        max_parts: int | None = None,
    ) -> Self:
        """Expose a capability at ``PUT path``."""
        return self.route(
            "PUT",
            path,
            capability,
            *bindings,
            openapi=openapi,
            max_body_bytes=max_body_bytes,
            max_parts=max_parts,
        )

    def patch(
        self,
        path: str,
        capability: CapabilityRef,
        *bindings: Binding,
        openapi: OpenApiOperation | None = None,
        max_body_bytes: int | None = None,
        max_parts: int | None = None,
    ) -> Self:
        """Expose a capability at ``PATCH path``."""
        return self.route(
            "PATCH",
            path,
            capability,
            *bindings,
            openapi=openapi,
            max_body_bytes=max_body_bytes,
            max_parts=max_parts,
        )

    def delete(
        self,
        path: str,
        capability: CapabilityRef,
        *bindings: Binding,
        openapi: OpenApiOperation | None = None,
    ) -> Self:
        """Expose a capability at ``DELETE path``."""
        return self.route("DELETE", path, capability, *bindings, openapi=openapi)

    def sse(
        self,
        path: str,
        capability: CapabilityRef,
        *bindings: Binding,
        max_event_bytes: int | None = None,
    ) -> Self:
        """Expose a streaming capability at ``GET path`` as server-sent events.

        This is the only supported SSE spelling, and it is deliberately not a
        response type an ordinary `get` could acquire: a capability can be
        projected through several adapters, so the wire representation belongs
        to the exposure that chose it (ADR 0085 D1).

        Each yielded unit becomes one standard ``message`` event carrying one
        compact JSON value, so a browser ``EventSource`` needs no Agnara
        vocabulary to read it. The response begins only once the first unit is
        representable, which is what keeps an ordinary RFC 9457 problem
        response available for a failure that exposed nothing. Every started
        response then ends with one ``agnara.terminal`` event naming the
        outcome and the exact number of units already sent, because a closed
        connection cannot tell completion from failure.

        Reconnection is a client transport behaviour and nothing more. This
        projection sends no ``id`` or ``retry`` field and gives
        ``Last-Event-ID`` no meaning: a reconnecting client starts a new,
        ordinary invocation, with every policy and effect rule applied again.

        Args:
            path: a route template such as ``/reports/{report_id}``.
            capability: a capability declared on the application with
                ``streaming=True``, either the decorated function or its
                `CapabilityDefinition`.
            bindings: one `Binding` per input the request supplies. Body, form
                and upload sources are refused: an ``EventSource`` issues a
                GET, and this projection supplies no request-body streaming
                contract.
            max_event_bytes: the ceiling for one encoded event, defaulting to
                the 1 MiB this adapter already uses for request bodies. A
                larger unit fails the response rather than being truncated or
                silently dropped.

        Returns:
            This builder, so declarations can be chained.

        Raises:
            HttpDefinitionError: the builder has already compiled, or an
                argument is not of the expected type. That the capability is
                streaming, and that no body binding was asked for, is checked
                at `compile`, when the plan exists.

        Note:
            An SSE route is absent from the OpenAPI document and accepts no
            `OpenApiOperation`. The document describes complete JSON
            representations and has no reviewed schema for stream units or for
            the terminal event, and claiming one would be exactly the
            accidental promise ADR 0085 D6 refuses to make.
        """
        if max_event_bytes is not None and (
            isinstance(max_event_bytes, bool) or not isinstance(max_event_bytes, int)
        ):
            raise HttpDefinitionError(f"GET {path}: max_event_bytes must be an integer or None")
        self.route("GET", path, capability, *bindings)
        declaration = self._declarations[-1]
        declaration.sse = True
        declaration.max_event_bytes = max_event_bytes
        return self

    def compile(
        self,
        capabilities: FrozenCapabilityRegistry,
        *,
        dependencies: DIRegistry | None = None,
        openapi: OpenApiInfo | None = None,
        openapi_path: str | None = None,
        documentation: HttpDocumentation | None = None,
        explorer: HttpExplorer | None = None,
        lifecycle: Lifecycle | None = None,
        request_timeout: float | None = None,
        problem_base_uri: str | None = None,
        hooks: Sequence[TelemetryHook] = (),
        confirmation_verifier: ConfirmationVerifier | None = None,
        schema_adapter: SchemaAdapter | None = None,
    ) -> HttpApplication:
        """Compile every declaration into one immutable ASGI application.

        This is the startup step. Everything reflective happens here: routes
        are parsed and checked for collisions, capabilities are resolved,
        execution plans are compiled, bindings are validated against each
        plan's inputs, and the result is frozen. A request then costs a trie
        lookup, a binding pass, one invocation and one serialization.

        The application owns the lifecycle around this call. It creates the
        `Agnara` app, declares capabilities, calls ``app.compile()`` to freeze
        them, and passes the result here. Nothing is registered globally and
        this object holds no module-level state, so two surfaces in one
        process are independent.

        Args:
            capabilities: the frozen registry from ``Agnara.compile()``. Every
                declared route is resolved against it.
            dependencies: the dependency registry to compile plans against.
                An empty registry is used when omitted, which is correct for
                capabilities that take no dependencies.
            openapi: document metadata. Without it,
                `HttpApplication.openapi` raises rather than inventing a
                title and version.
            openapi_path: serve the document at this path, for example
                ``"/openapi.json"``. Omitted means the document is not served;
                publishing an API description is a deliberate act (ADR 0035),
                so there is no default path.
            documentation: typed OpenAPI schema and built-in UI selections.
                ``HttpDocumentation()`` publishes ``/openapi.json`` and local
                Swagger UI at ``/docs``; individual selections may be ``None``.
            explorer: an independently authorized, read-only Explorer route.
            lifecycle: an async context manager factory run once per ASGI
                lifespan cycle. Startup enters it, shutdown exits it.
                HTTP-owned singleton providers close before it exits. Without
                a callback, lifespan still owns dependency cleanup.
                Application state belongs in dependency providers, which is
                why the lifecycle cannot hand a value back.
            request_timeout: a deadline in seconds for the capability
                invocation, enforced by the runtime and reported as a timeout
                failure. It starts once the request has been bound, so it
                bounds execution rather than how long a client may take to
                send its body; that belongs to the ASGI server or the proxy in
                front of it (`docs/THREAT_MODEL.md`).
            problem_base_uri: an absolute URI prefix for RFC 9457 problem
                types. Without it every problem keeps the standard
                ``about:blank`` type and the ``code`` extension member stays
                the machine-readable discriminator.
            hooks: telemetry hooks passed to each compiled plan.
            confirmation_verifier: required by any capability that declares
                confirmation.
            schema_adapter: an alternative schema port implementation.

        Returns:
            The compiled `HttpApplication`.

        Raises:
            HttpDefinitionError: a route collides, a path template is invalid,
                an input has no binding or an unsupported one, or the surface
                cannot be projected into OpenAPI. The adapter's own diagnostic
                is on ``__cause__``.
            DefinitionError: a capability is not declared on this registry, or
                its execution plan cannot be compiled. Raised unchanged,
                because it is already a public core error describing a
                capability rather than an HTTP mistake.
        """
        if not isinstance(capabilities, FrozenCapabilityRegistry):
            raise HttpDefinitionError(
                "compile needs the frozen capability registry from Agnara.compile(), got "
                f"{type(capabilities).__name__}"
            )
        if dependencies is None:
            dependencies = DIRegistry()
        if not isinstance(dependencies, DIRegistry):
            raise HttpDefinitionError(
                f"dependencies must be a DIRegistry or None, got {type(dependencies).__name__}"
            )
        if openapi is not None and not isinstance(openapi, OpenApiInfo):
            raise HttpDefinitionError(
                f"openapi must be an OpenApiInfo or None, got {type(openapi).__name__}"
            )
        if openapi_path is not None and openapi is None:
            raise HttpDefinitionError(
                "openapi_path serves an OpenAPI document, so it needs "
                "openapi=OpenApiInfo(title, version)"
            )
        if documentation is not None and not isinstance(documentation, HttpDocumentation):
            raise HttpDefinitionError(
                "documentation must be an HttpDocumentation or None, got "
                f"{type(documentation).__name__}"
            )
        if documentation is not None and openapi is None:
            raise HttpDefinitionError(
                "documentation needs openapi=OpenApiInfo(title, version) to generate its contract"
            )
        if documentation is not None and openapi_path is not None:
            raise HttpDefinitionError(
                "openapi_path and documentation are alternative schema-publication configurations; "
                "use HttpDocumentation(schema=OpenApiSchema(...))"
            )
        if explorer is not None and not isinstance(explorer, HttpExplorer):
            raise HttpDefinitionError(
                f"explorer must be an HttpExplorer or None, got {type(explorer).__name__}"
            )
        if lifecycle is not None and not callable(lifecycle):
            raise HttpDefinitionError(
                f"lifecycle must be callable or None, got {type(lifecycle).__name__}"
            )

        # Resolve every declaration once. Doing it per use would let one
        # declaration report a different capability in the route table than in
        # the exposure records, which is exactly the drift ADR 0070 removed.
        resolved = [
            (declaration, self._capability_id(capabilities, declaration))
            for declaration in self._declarations
        ]
        plans = self._plans(
            resolved, dependencies, hooks, confirmation_verifier, schema_adapter, capabilities
        )
        exposures = [
            _HTTPExposure(
                declaration.method,
                declaration.path,
                plans[capability_id],
                tuple(binding._internal() for binding in declaration.bindings),
                **_limits(declaration),
                openapi=None if declaration.openapi is None else declaration.openapi._internal(),
                sse=declaration.projection(),
            )
            for declaration, capability_id in resolved
        ]

        try:
            compilation = _compile_exposure_surface(exposures, surface=self._surface.name)
            routes = compilation.runtime
            options = _DispatchOptions(
                problem_types=_compile_problem_types(problem_base_uri),
                timeout=request_timeout,
            )
            container = DIContainer(dependencies)
            dispatch = _HTTPDispatcher(routes, container, options)
            static_surfaces, documentation_routes = self._documentation_surfaces(
                openapi, openapi_path, documentation, routes
            )
            static_dispatch = _SurfaceDispatcher(
                _compile_surfaces(static_surfaces, routes),
                dispatch,
                problem_types=options.problem_types,
            )
            published: Callable[[_Scope, Callable[[], Any], Callable[[Any], Any]], Any] = (
                _DocumentationDispatcher(
                    documentation_routes,
                    static_dispatch,
                    problem_types=options.problem_types,
                )
                if documentation_routes
                else static_dispatch
            )
            if explorer is not None:
                compiled_explorer = _compile_explorer(
                    _ExplorerRoute(
                        base_path=explorer.path,
                        snapshot=explorer.snapshot,
                        visibility=explorer.visibility,
                        principals=explorer.principals,
                        challenge=explorer.challenge,
                        allow_anonymous=explorer.allow_anonymous,
                        cache_control=explorer.cache_control,
                    ),
                    routes,
                )
                self._check_explorer_collisions(compiled_explorer.base_path, static_surfaces)
                published = _ExplorerDispatcher(
                    compiled_explorer,
                    published,
                    problem_types=options.problem_types,
                )
            boundary = _ASGIBoundary(
                published,
                _LifespanDispatcher(lambda: _owned_lifecycle(container, lifecycle)),
            )
            if openapi is not None and openapi_path is None and documentation is None:
                # Not served, but still promised: `HttpApplication.openapi()`
                # projects on demand, and a surface it cannot describe is a
                # startup failure, not one the first caller of that method finds.
                _project_openapi(routes, openapi._internal())
        except _TRANSLATED as error:
            raise HttpDefinitionError(str(error)) from error
        except ValueError as error:
            # A defensive net: an adapter-internal ValueError must not reach an
            # application as an anonymous ValueError from a private module.
            raise HttpDefinitionError(str(error)) from error

        # Closed only now: a compile that failed left nothing compiled, and the
        # declaration it refused can be corrected and compiled again.
        self._frozen = True
        return HttpApplication(
            self._surface,
            boundary,
            routes,
            compilation,
            tuple(plans.values()),
            openapi,
        )

    def _documentation_surfaces(
        self,
        openapi: OpenApiInfo | None,
        openapi_path: str | None,
        documentation: HttpDocumentation | None,
        routes: _Routes,
    ) -> tuple[tuple[_HTTPSurface, ...], tuple[_DocumentationRoute, ...]]:
        """Compile every static documentation reservation before serving it."""
        if openapi is None:
            return (), ()
        document = json.dumps(
            _project_openapi(routes, openapi._internal()),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if documentation is None:
            if openapi_path is None:
                return (), ()
            return (
                _HTTPSurface(
                    "openapi",
                    openapi_path,
                    "application/json; charset=utf-8",
                    document,
                    ((b"cache-control", b"no-store"),),
                ),
            ), ()

        surfaces: list[_HTTPSurface] = []
        if documentation.schema is not None:
            surfaces.append(
                _HTTPSurface(
                    "openapi",
                    documentation.schema.path,
                    "application/json; charset=utf-8",
                    document,
                    ((b"cache-control", b"no-store"),),
                )
            )
        selected: list[tuple[str, SwaggerUI | Scalar | ReDoc]] = []
        if documentation.swagger is not None:
            selected.append(("swagger-ui", documentation.swagger))
        if documentation.scalar is not None:
            selected.append(("scalar", documentation.scalar))
        if documentation.redoc is not None:
            selected.append(("redoc", documentation.redoc))
        compiled_routes: list[_DocumentationRoute] = []
        for name, selection in selected:
            if not isinstance(selection.path, str) or not selection.path.startswith("/"):
                raise HttpDefinitionError(f"{name} path must be a same-origin absolute path")
            if not isinstance(selection.assets, DocumentationAssets):
                raise HttpDefinitionError(f"{name} assets must be a DocumentationAssets")
            if not isinstance(getattr(selection, "try_it", False), bool):
                raise HttpDefinitionError(f"{name} try_it must be a boolean")
            assets_path = (
                "/assets" if selection.path == "/" else f"{selection.path.rstrip('/')}/assets"
            )
            provider = (
                _SwaggerUIProvider(cdn=selection.assets.remote_assets)
                if isinstance(selection, SwaggerUI)
                else _ScalarProvider(cdn=selection.assets.remote_assets)
                if isinstance(selection, Scalar)
                else _ReDocProvider(cdn=selection.assets.remote_assets)
            )
            route = _DocumentationRoute(
                name=provider.name,
                path=selection.path,
                assets_path=assets_path,
                provider=provider,
                artifact=document,
                openapi_version="3.2.0",
                title=openapi.title,
                schema_path=None if documentation.schema is None else documentation.schema.path,
                allowed_remote_origins=selection.assets.allowed_remote_origins,
                try_it=getattr(selection, "try_it", False),
            )
            page = _render_documentation_page(route, {"root_path": ""})
            surfaces.append(
                _HTTPSurface(
                    f"documentation.{name}.page",
                    route.path,
                    "text/html; charset=utf-8",
                    page.html,
                    _documentation_security_headers(page.csp),
                )
            )
            for index, (asset_name, asset) in enumerate(sorted(page.assets.items())):
                surfaces.append(
                    _HTTPSurface(
                        f"documentation.{name}.asset.{index}",
                        f"{route.assets_path}/{asset_name}",
                        asset.media_type,
                        asset.body,
                        ((b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")),
                    )
                )
            compiled_routes.append(route)
        return tuple(surfaces), tuple(compiled_routes)

    def _check_explorer_collisions(self, base_path: str, surfaces: Sequence[_HTTPSurface]) -> None:
        """Explorer owns a subtree, so no static surface may live inside it."""
        prefix = f"{base_path}/"
        for surface in sorted(surfaces, key=lambda item: (item.path, item.name)):
            if surface.path == base_path or surface.path.startswith(prefix):
                raise _SurfaceDefinitionError(
                    f"Explorer at {base_path!r} would shadow HTTP surface "
                    f"{surface.name!r} at {surface.path!r}"
                )

    def _plans(
        self,
        resolved: Sequence[tuple[_Declaration, CapabilityId]],
        dependencies: DIRegistry,
        hooks: Sequence[TelemetryHook],
        confirmation_verifier: ConfirmationVerifier | None,
        schema_adapter: SchemaAdapter | None,
        capabilities: FrozenCapabilityRegistry,
    ) -> dict[CapabilityId, ExecutionPlan]:
        """Compile one plan per distinct capability, whatever its route count.

        Two routes onto one capability share a plan. Compiling twice would
        produce two objects the introspection layer reports as duplicate plans
        for one capability, which it refuses.
        """
        compiled: dict[CapabilityId, ExecutionPlan] = {}
        for _, capability_id in resolved:
            if capability_id in compiled:
                continue
            compiled[capability_id] = ExecutionPlan.compile(
                capabilities[capability_id],
                dependencies,
                hooks,
                confirmation_verifier,
                schema_adapter,
            )
        return compiled

    def _capability_id(
        self,
        capabilities: FrozenCapabilityRegistry,
        declaration: _Declaration,
    ) -> CapabilityId:
        """Resolve one declaration's capability against the frozen registry."""
        target = declaration.target
        if isinstance(target, CapabilityDefinition):
            registered = capabilities.get(target.id)
            if registered is not target:
                raise DefinitionError(
                    f"{declaration.describe()}: capability {target.id} is not declared on the "
                    "registry passed to compile()"
                )
            return target.id
        if not callable(target):
            raise HttpDefinitionError(
                f"{declaration.describe()}: expects a declared capability callable or "
                f"CapabilityDefinition, got {type(target).__name__}"
            )
        matches = [
            capability_id
            for capability_id in capabilities
            if capabilities[capability_id].handler is target
        ]
        if not matches:
            raise DefinitionError(
                f"{declaration.describe()}: "
                f"{getattr(target, '__name__', repr(target))!r} is not a declared capability"
            )
        if len(matches) > 1:
            named = ", ".join(str(capability_id) for capability_id in matches)
            raise DefinitionError(
                f"{declaration.describe()}: that callable is declared as several capabilities "
                f"({named}); pass a CapabilityDefinition to select one"
            )
        return matches[0]

    def __len__(self) -> int:
        return len(self._declarations)

    def __repr__(self) -> str:
        state = "compiled" if self._frozen else "open"
        return f"Http({self._surface.name!r}, {len(self._declarations)} routes, {state})"
