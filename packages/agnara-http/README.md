# agnara-http

HTTP/ASGI exposure adapter. Owns routing, request decoding, response encoding, RFC 9457 mapping and OpenAPI generation.

OpenAPI 3.2 is projected from compiled HTTP exposures and shared capability
schemas. Optional browser documentation providers consume that generated
contract; Swagger UI, ReDoc, Scalar or any other UI must remain replaceable
and must not become a dependency of `agnara-core`.

Agnara Explorer is not an OpenAPI renderer. If it is initially served through
this adapter, it consumes the filtered protocol-neutral introspection snapshot
defined by the core/application composition boundary.

The package now contains the dependency-free internal ASGI 3 single-callable
boundary delivered by E6.1. It accepts HTTP scopes and delegates their raw
`scope`, `receive` and `send` objects to the adapter's dispatcher. Unsupported
protocols are rejected explicitly instead of being mistaken for supported
lifespan or WebSocket behavior.

E6.2 adds the internal two-phase route registry used by that future
dispatcher. Startup registration validates methods and segment parameters,
detects duplicate or structurally ambiguous templates, and freezes into an
immutable per-method trie. Runtime matching prefers static segments, captures
raw decoded path segments, preserves significant trailing slashes, and exposes
allowed methods in deterministic registration order.

E6.3 adds an internal compiled request-binding boundary. Every capability
input is assigned explicitly to a path segment, query parameter, header, or a
single JSON body during startup. Runtime binding performs strict query
percent/UTF-8 decoding, case-insensitive header lookup, documented scalar wire
conversion, bounded chunked JSON reads, and deterministic duplicate/error
handling. It produces an invocation payload for the shared core validation
path and never substitutes for capability schema validation. Multipart, forms,
files, cookies, public exposure syntax, and HTTP response mapping remain out of
scope.

E6.4 adds deterministic internal success-response serialization. Successful
values are projected recursively to compact UTF-8 JSON and emitted as one ASGI
response-start event followed by one terminal body event. `None` produces a
bodyless `204`; `HEAD` preserves the equivalent representation headers while
suppressing transmitted body bytes. The complete value is checked before the
response starts, including cycles, finite numbers and string-only object keys.
Canonical failures remain explicitly unsupported here because E6.5 owns their
RFC 9457 mapping.

The design baseline is ASGI 3.0 and the HTTP/WebSocket sub-specification 2.5:

- https://asgi.readthedocs.io/en/latest/specs/main.html
- https://asgi.readthedocs.io/en/latest/specs/www.html

This is not yet a public HTTP composition API or a complete ASGI/HTTP
conformance claim. Failure serialization, lifespan, OpenAPI generation,
documentation providers and Explorer remain separate roadmap work; see RFC
0003, ADR 0018, EPIC 6 and EPIC 8.

- Import package: `agnara_http`
- Depends on: `agnara-core`
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.
