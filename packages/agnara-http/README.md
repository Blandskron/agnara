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
Canonical failures are serialized by the separate RFC 9457 boundary below.

E6.5 adds internal RFC 9457 failure mapping. Every `FailureCode` is projected
through one explicit, exhaustive table to a reviewed HTTP status and an
occurrence-independent problem `title`, and emitted as
`application/problem+json` with the same deterministic compact UTF-8 JSON
encoding used for success. The stable machine-readable discriminator is the
`code` extension member, so applications that publish no problem
documentation keep the RFC 9457 default `about:blank` type; an application may
instead compile an explicit absolute base URI into one type URI per code.
Failure details are nested under a single `details` member so they cannot
shadow a reserved member, `internal_failure` never serializes handler message
or details, and a prebuilt last-resort internal problem response is available
to a dispatcher that cannot serialize an outcome. `WWW-Authenticate`,
`Retry-After`, content negotiation, `problem+xml` and multi-error arrays are
documented gaps rather than conformance claims; see ADR 0028.

E6.6a adds transport-level problems: the failures that happen before a
capability runs. Binding failures now carry a reason rather than only a
message, so a dispatcher selects a status from a contract instead of matching
text: malformed data becomes `400`, an unacceptable media type `415`, an
oversized body `413`, and a client disconnect becomes no response at all. A
missing route becomes `404` and a method mismatch `405` with the `Allow`
header RFC 9110 requires, attached during serialization so it cannot be
dropped at emission. Capability and transport failures share one problem-type
namespace keyed by the `code` extension, because `code` is what a client
reads. `401` and `429` stay absent until authentication and rate limiting
exist; see ADR 0030.

E6.6b is the request path itself. A declared exposure carries a method, a
path template, an `ExecutionPlan`, its input bindings and a body limit;
compilation validates all of it against the capability's real input schemas
and freezes an immutable registry, so a matched route resolves to its plan and
binding in one lookup and every declaration error fails at startup. Dispatch
then matches, binds, invokes and serializes with no reflection and no lock.
`HEAD` falls back to a `GET` exposure and suppresses only body bytes;
`root_path` is stripped so an application can be mounted; a client disconnect
produces no response; and a serialization failure falls back to the prebuilt
internal problem, which is the case that constant exists for. The problem
`instance` carries the path but never the query string, so a secret passed in
a query cannot be copied into a problem body. Every invocation runs as the
anonymous principal, which is why no path here produces a `401`; see ADR 0031.

The design baseline is ASGI 3.0 and the HTTP/WebSocket sub-specification 2.5:

- https://asgi.readthedocs.io/en/latest/specs/main.html
- https://asgi.readthedocs.io/en/latest/specs/www.html

This is not yet a public HTTP composition API or a complete ASGI/HTTP
conformance claim. Lifespan, OpenAPI generation, documentation providers and
Explorer remain separate roadmap work; see RFC 0003, ADR 0018, EPIC 6 and
EPIC 8.

- Import package: `agnara_http`
- Depends on: `agnara-core`
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.
