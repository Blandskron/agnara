"""HTTP/ASGI exposure adapter for Agnara capabilities.

Owns the ASGI boundary, routing, request decoding, response encoding, HTTP
lifecycle, RFC 9457 failure mapping, OpenAPI generation, the authorized
introspection discovery endpoint and the read-only Agnara Explorer.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` sections 3 and 4, and EPIC 6 in ``BACKLOG.md``.
"""

#: This distribution intentionally exports nothing yet. The adapter is fully
#: implemented behind private modules, but its user-facing composition surface
#: is still the golden-design sketch in ``docs/API_DESIGN.md`` section 4 and is
#: not stable syntax. Declaring the empty surface explicitly keeps "no public
#: API yet" distinguishable from "someone forgot ``__all__``".
__all__: list[str] = []
