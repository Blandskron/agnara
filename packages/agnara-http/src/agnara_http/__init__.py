"""HTTP/ASGI exposure adapter for Agnara capabilities.

Owns the ASGI boundary, routing, request decoding, response encoding, HTTP
lifecycle, RFC 9457 failure mapping, OpenAPI generation, the authorized
introspection discovery endpoint and the read-only Agnara Explorer.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` sections 3 and 4, and EPIC 6 in ``BACKLOG.md``.

The public surface is the composition API in ``agnara_http.composition`` and
nothing else. ``docs/HTTP_COMPOSITION.md`` is the supported usage guide and
records what ``0.1.0a4`` does not yet expose: the documentation UI providers,
the Agnara Explorer and the authorized discovery endpoint remain internal,
because the publication plan compiles placeholder routes and no product code
path renders a provider. Every other module here is underscore-prefixed and
carries no compatibility promise.
"""

from .composition import (
    Binding,
    BindingSource,
    Http,
    HttpApplication,
    HttpDefinitionError,
    OpenApiInfo,
    OpenApiOperation,
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
