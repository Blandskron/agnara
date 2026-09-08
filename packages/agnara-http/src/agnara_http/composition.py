"""The supported way to expose Agnara capabilities over HTTP.

This is the whole public surface of ``agnara-http``. Everything else in the
package is an underscore-prefixed implementation detail, and the point of this
module is that an application never has to reach for one.

Seven names, because the package exported nothing until the exposure model
beneath it was settled (ADR 0070) and a small contract is easier to keep than
a wide one:

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

A worked example lives in ``docs/HTTP_COMPOSITION.md``; the short version::

    app = Agnara("billing")


    @app.capability
    def refund(payment_id: str) -> str: ...


    http = Http()
    http.post("/refunds", refund, Binding("payment_id", BindingSource.QUERY))
    asgi = http.compile(app.compile(), openapi=OpenApiInfo("Billing", "1.0"))

Nothing here is stable syntax. Every name is ``provisional`` in
``docs/PUBLIC_API.md``: these are the deliberate entry points, and the alpha
line makes no compatibility promise about them.

The public value types are translated into the adapter's internal ones rather
than aliasing them. That is deliberate: it is what lets routing, binding and
projection change shape without breaking an application, which is the reason
this package declared no public surface for three releases.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from enum import StrEnum
from typing import Any, Self

from agnara import CapabilityDefinition, DefinitionError, FrozenCapabilityRegistry
from agnara.capability import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import ExecutionPlan, TelemetryHook
from agnara.exposure import SurfaceCompilation, SurfaceId
from agnara.policy import ConfirmationVerifier
from agnara.schema import SchemaAdapter
from agnara_http._asgi import _ASGIBoundary
from agnara_http._binding import _BindingDefinitionError, _BindingSource, _InputBinding
from agnara_http._dispatch import (
    _CompiledExposure,
    _DispatchOptions,
    _HTTPDispatcher,
    _HTTPExposure,
    _OpenAPIPublication,
)
from agnara_http._exposures import DEFAULT_SURFACE, _compile_exposure_surface
from agnara_http._lifespan import _LifespanDispatcher
from agnara_http._openapi import _OpenAPIDefinitionError, _OpenAPIInfo, _project_openapi
from agnara_http._problem import _compile_problem_types, _ProblemDefinitionError
from agnara_http._routing import (
    _FrozenRouteRegistry,
    _RouteDefinitionError,
    _RouteRegistryFrozenError,
)
from agnara_http._surfaces import (
    _compile_surfaces,
    _HTTPSurface,
    _SurfaceDefinitionError,
    _SurfaceDispatcher,
)

__all__ = [
    "Binding",
    "BindingSource",
    "Http",
    "HttpApplication",
    "HttpDefinitionError",
    "OpenApiInfo",
    "OpenApiOperation",
]

#: Adapter-internal failures translated into `HttpDefinitionError`.
#:
#: A public API should not hand back `_BindingDefinitionError` or
#: `_RouteRegistryFrozenError`: an application would end up naming a private
#: type in an `except` clause, which is the coupling this module exists to
#: remove. The original stays on `__cause__`, so nothing is hidden from
#: whoever is debugging.
_TRANSLATED: tuple[type[Exception], ...] = (
    _BindingDefinitionError,
    _OpenAPIDefinitionError,
    _ProblemDefinitionError,
    _RouteDefinitionError,
    _RouteRegistryFrozenError,
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
        "max_parts",
        "method",
        "openapi",
        "path",
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
    ) -> None:
        self.method = method
        self.path = path
        self.target = target
        self.bindings = bindings
        self.openapi = openapi
        self.max_body_bytes = max_body_bytes
        self.max_parts = max_parts

    def describe(self) -> str:
        return f"{self.method} {self.path}"


class HttpApplication:
    """One compiled HTTP surface: an immutable ASGI 3 application.

    Call it the way any ASGI server does::

        uvicorn.run(asgi)  # or: hypercorn, granian, daphne

    Being ASGI is a boundary, not an integration. Agnara speaks ASGI 3 and
    nothing here promises support for a specific framework; that is
    `0.1.0b1` (ADR 0068).

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

    def compile(
        self,
        capabilities: FrozenCapabilityRegistry,
        *,
        dependencies: DIRegistry | None = None,
        openapi: OpenApiInfo | None = None,
        openapi_path: str | None = None,
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
            boundary = _ASGIBoundary(
                _SurfaceDispatcher(
                    _compile_surfaces(self._static_surfaces(openapi, openapi_path, routes), routes),
                    dispatch,
                    problem_types=options.problem_types,
                ),
                _LifespanDispatcher(lambda: _owned_lifecycle(container, lifecycle)),
            )
            if openapi is not None and openapi_path is None:
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

    def _static_surfaces(
        self,
        openapi: OpenApiInfo | None,
        openapi_path: str | None,
        routes: _Routes,
    ) -> tuple[_HTTPSurface, ...]:
        """The document route, when the application asked for one."""
        if openapi_path is None or openapi is None:
            return ()
        document = json.dumps(
            _project_openapi(routes, openapi._internal()),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return (
            _HTTPSurface(
                "openapi",
                openapi_path,
                "application/json; charset=utf-8",
                document,
                ((b"cache-control", b"no-store"),),
            ),
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
