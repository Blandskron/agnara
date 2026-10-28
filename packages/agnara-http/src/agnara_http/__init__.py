"""HTTP/ASGI exposure adapter for Agnara capabilities.

Owns the ASGI boundary, routing, request decoding, response encoding, HTTP
lifecycle, RFC 9457 failure mapping, OpenAPI generation, the authorized
introspection discovery endpoint and the read-only Agnara Explorer.

Depends on ``agnara``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` for boundaries and ``docs/MATURITY.md`` for status.

The public surface is the fourteen-name composition API at the package root,
``agnara_http``. The ``composition`` module is its implementation, not a second
supported import path. ``docs/HTTP_COMPOSITION.md`` is the supported usage guide and
includes typed configuration for generated OpenAPI, built-in documentation UIs
and the separately authorized read-only Explorer. Third-party providers and
the discovery endpoint remain internal. Every other module here is
an implementation detail and carries no separate compatibility promise.
"""

from .composition import (
    Binding,
    BindingSource,
    DocumentationAssets,
    Http,
    HttpApplication,
    HttpDefinitionError,
    HttpDocumentation,
    HttpExplorer,
    OpenApiInfo,
    OpenApiOperation,
    OpenApiSchema,
    ReDoc,
    Scalar,
    SwaggerUI,
)

__all__ = [
    "Binding",
    "BindingSource",
    "DocumentationAssets",
    "Http",
    "HttpApplication",
    "HttpDefinitionError",
    "HttpDocumentation",
    "HttpExplorer",
    "OpenApiInfo",
    "OpenApiOperation",
    "OpenApiSchema",
    "ReDoc",
    "Scalar",
    "SwaggerUI",
]
