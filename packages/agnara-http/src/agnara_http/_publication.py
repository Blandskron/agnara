"""Independent selection of HTTP documentation and discovery surfaces.

The configuration in this module is internal until the public HTTP
composition API is reviewed.  A surface is enabled by supplying its own typed
configuration and disabled by absence; there is no global documentation flag
whose meaning changes several publication decisions at once.

This module prepares already-filtered static surfaces and provider requests.
It does not render a provider, serve provider assets, define Explorer
semantics, or grant visibility or invocation authority.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agnara_http._dispatch import _CompiledExposure
from agnara_http._documentation import (
    _PROVIDER_NAME,
    _DocumentationDefinitionError,
    _DocumentationRequest,
)
from agnara_http._routing import _FrozenRouteRegistry
from agnara_http._surfaces import _compile_surfaces, _HTTPSurface, _SurfaceDefinitionError


class _PublicationDefinitionError(ValueError):
    """A documentation publication selection is incomplete or contradictory."""


@dataclass(frozen=True, slots=True)
class _OpenAPIArtifact:
    """One already-filtered serialized OpenAPI document and its exact version."""

    version: str
    document: bytes

    def __post_init__(self) -> None:
        if (
            not isinstance(self.version, str)
            or not self.version.strip()
            or self.version != self.version.strip()
        ):
            raise _PublicationDefinitionError("OpenAPI artifact version must be non-empty")
        if not isinstance(self.document, bytes) or not self.document:
            raise _PublicationDefinitionError("OpenAPI artifact document must be non-empty bytes")
        try:
            serialized = self.document.decode("utf-8")
            decoded: Any = json.loads(serialized)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise _PublicationDefinitionError(
                "OpenAPI artifact document must be valid UTF-8 JSON"
            ) from error
        if not isinstance(decoded, dict):
            raise _PublicationDefinitionError("OpenAPI artifact document must be a JSON object")
        if decoded.get("openapi") != self.version:
            raise _PublicationDefinitionError(
                f"OpenAPI artifact declares {decoded.get('openapi')!r}, not {self.version!r}"
            )


@dataclass(frozen=True, slots=True)
class _SchemaRoute:
    """Presence enables serving the configured OpenAPI artifact at this path."""

    path: str
    headers: tuple[tuple[bytes, bytes], ...] = ()


@dataclass(frozen=True, slots=True)
class _DocumentationUIRoute:
    """Presence enables one named provider request at one explicit path."""

    provider_name: str
    path: str
    assets_url: str
    title: str
    try_it: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.provider_name, str) or not _PROVIDER_NAME.fullmatch(
            self.provider_name
        ):
            raise _PublicationDefinitionError(
                f"invalid documentation provider name: {self.provider_name!r}"
            )
        if not isinstance(self.try_it, bool):
            raise _PublicationDefinitionError("documentation try_it must be a boolean")


@dataclass(frozen=True, slots=True)
class _ExplorerRoute:
    """Presence enables one already-rendered, already-filtered Explorer shell."""

    path: str
    html: bytes
    headers: tuple[tuple[bytes, bytes], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.html, bytes) or not self.html:
            raise _PublicationDefinitionError("Explorer html must be non-empty bytes")


@dataclass(frozen=True, slots=True)
class _PublicationConfiguration:
    """Independent optional selections; absence means disabled."""

    openapi: _OpenAPIArtifact | None = None
    schema: _SchemaRoute | None = None
    documentation: tuple[_DocumentationUIRoute, ...] = ()
    explorer: _ExplorerRoute | None = None

    def __post_init__(self) -> None:
        if self.openapi is not None and not isinstance(self.openapi, _OpenAPIArtifact):
            raise _PublicationDefinitionError("openapi must be an _OpenAPIArtifact or None")
        if self.schema is not None and not isinstance(self.schema, _SchemaRoute):
            raise _PublicationDefinitionError("schema must be a _SchemaRoute or None")
        if not isinstance(self.documentation, tuple) or any(
            not isinstance(route, _DocumentationUIRoute) for route in self.documentation
        ):
            raise _PublicationDefinitionError(
                "documentation must be a tuple of _DocumentationUIRoute values"
            )
        if self.explorer is not None and not isinstance(self.explorer, _ExplorerRoute):
            raise _PublicationDefinitionError("explorer must be an _ExplorerRoute or None")


@dataclass(frozen=True, slots=True)
class _DocumentationRender:
    """One selected UI provider and the request it will render downstream."""

    provider_name: str
    path: str
    request: _DocumentationRequest


@dataclass(frozen=True, slots=True)
class _CompiledPublicationPlan:
    """Only the selected static surfaces and provider render requests."""

    surfaces: tuple[_HTTPSurface, ...]
    documentation: tuple[_DocumentationRender, ...]


def _compile_publication(
    configuration: _PublicationConfiguration,
    capability_routes: _FrozenRouteRegistry[_CompiledExposure],
) -> _CompiledPublicationPlan:
    """Compile one deterministic publication plan without rendering a provider."""
    if not isinstance(configuration, _PublicationConfiguration):
        raise TypeError(
            f"configuration must be a _PublicationConfiguration, got {type(configuration).__name__}"
        )
    if not isinstance(capability_routes, _FrozenRouteRegistry):
        raise TypeError(
            f"capability_routes must be a frozen registry, got {type(capability_routes).__name__}"
        )

    artifact = configuration.openapi
    if (configuration.schema is not None or configuration.documentation) and artifact is None:
        raise _PublicationDefinitionError(
            "schema and documentation UI routes require an OpenAPI artifact"
        )

    static_surfaces: list[_HTTPSurface] = []
    reservations: list[_HTTPSurface] = []
    if configuration.schema is not None:
        assert artifact is not None
        schema = _surface(
            "schema",
            configuration.schema.path,
            "application/json; charset=utf-8",
            artifact.document,
            configuration.schema.headers,
        )
        static_surfaces.append(schema)
        reservations.append(schema)

    if configuration.explorer is not None:
        explorer = _surface(
            "explorer",
            configuration.explorer.path,
            "text/html; charset=utf-8",
            configuration.explorer.html,
            configuration.explorer.headers,
        )
        static_surfaces.append(explorer)
        reservations.append(explorer)

    documentation: list[_DocumentationRender] = []
    for route in sorted(
        configuration.documentation,
        key=lambda candidate: (candidate.provider_name, candidate.path),
    ):
        assert artifact is not None
        document_url = configuration.schema.path if configuration.schema is not None else None
        document = None if document_url is not None else artifact.document
        request = _documentation_request(
            document_url=document_url,
            title=route.title,
            assets_url=route.assets_url,
            openapi_version=artifact.version,
            document=document,
            try_it=route.try_it,
        )
        documentation.append(_DocumentationRender(route.provider_name, route.path, request))
        # A provider will replace this placeholder with its rendered page in a
        # later delivery.  Compiling it now reserves and validates the route
        # without pretending an empty page is dispatchable.
        reservations.append(
            _surface(
                f"documentation.{route.provider_name}",
                route.path,
                "text/html; charset=utf-8",
                b"",
            )
        )

    # Reuse the one application-wide collision boundary from E6.13.  The
    # compiled placeholder registry is deliberately discarded: provider
    # rendering, CSP and assets are downstream work.
    try:
        _compile_surfaces(tuple(reservations), capability_routes)
    except _SurfaceDefinitionError as error:
        raise _PublicationDefinitionError(str(error)) from error
    return _CompiledPublicationPlan(
        surfaces=tuple(sorted(static_surfaces, key=lambda item: (item.path, item.name))),
        documentation=tuple(documentation),
    )


def _surface(
    name: str,
    path: str,
    media_type: str,
    body: bytes,
    headers: tuple[tuple[bytes, bytes], ...] = (),
) -> _HTTPSurface:
    """Translate surface validation into this configuration boundary's error."""
    try:
        return _HTTPSurface(name, path, media_type, body, headers)
    except _SurfaceDefinitionError as error:
        raise _PublicationDefinitionError(str(error)) from error


def _documentation_request(
    *,
    document_url: str | None,
    title: str,
    assets_url: str,
    openapi_version: str,
    document: bytes | None,
    try_it: bool,
) -> _DocumentationRequest:
    """Translate provider-request validation into this configuration boundary."""
    try:
        return _DocumentationRequest(
            document_url=document_url,
            title=title,
            assets_url=assets_url,
            openapi_version=openapi_version,
            document=document,
            try_it=try_it,
        )
    except _DocumentationDefinitionError as error:
        raise _PublicationDefinitionError(str(error)) from error
