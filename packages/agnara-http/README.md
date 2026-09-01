# agnara-http

HTTP/ASGI exposure adapter. Owns routing, request decoding, response encoding, RFC 9457 mapping and OpenAPI generation.

- Import package: `agnara_http`
- Depends on: `agnara-core`
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.
