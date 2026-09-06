"""HTTP/ASGI exposure adapter for Agnara capabilities.

Owns the ASGI boundary, routing, request decoding, response encoding, HTTP
lifecycle, RFC 9457 failure mapping, OpenAPI generation, the authorized
introspection discovery endpoint and the read-only Agnara Explorer.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` sections 3 and 4, and EPIC 6 in ``BACKLOG.md``.
"""
