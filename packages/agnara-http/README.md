# agnara-http

HTTP/ASGI exposure adapter. Owns routing, request decoding, response encoding, RFC 9457 mapping and OpenAPI generation.

OpenAPI 3.2 is projected from compiled HTTP exposures and shared capability
schemas. Optional browser documentation providers consume that generated
contract; Swagger UI, ReDoc, Scalar or any other UI must remain replaceable
and must not become a dependency of `agnara-core`.

Agnara Explorer is not an OpenAPI renderer. If it is initially served through
this adapter, it consumes the filtered protocol-neutral introspection snapshot
defined by the core/application composition boundary.

The package currently contains boundary scaffolding only. Generation,
providers, routes and Explorer are roadmap work; see RFC 0003, ADR 0018,
EPIC 6 and EPIC 8.

- Import package: `agnara_http`
- Depends on: `agnara-core`
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.
