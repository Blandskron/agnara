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

E6.7 adds a dependency-free internal OpenAPI 3.2.0 projection from that same
compiled exposure registry. An exposure is absent by default and contributes
paths, identifiers, descriptions, tags and schemas only through explicit
publication metadata; filtering happens before document assembly. Parameters
and JSON request bodies reuse the capability plan's compiled input schemas.
The current response projection truthfully remains generic because the runtime
does not yet compile output schemas: `200` carries an unconstrained JSON value,
`204` carries no value, and a default RFC 9457 response references one shared
problem component. Compact sorted-key UTF-8 serialization is byte-stable for
identical compiled input. This does not add a schema route, CLI export, UI,
viewer-specific authorization or a complete conformance claim; see ADR 0032.

E6.12 adds the documentation-provider contract. ADR 0018 and RFC 0003 decided
that browser documentation sits behind an optional, replaceable boundary; this
is that boundary in code, so its guarantees are enforced rather than trusted.
A provider is given an already-filtered document or its local URL and nothing
that could reveal more: no route registry, no compiled exposure, no execution
plan, no capability. It must name the OpenAPI versions it was tested against
and the features it does not support, because a compatibility claim made by
silence is the one this project refuses. Asked for a version it does not
support, it becomes unavailable with a diagnostic instead of rendering
documentation that is wrong. The network is opt-in twice, once by the provider
declaring remote assets and once by the deployment permitting them, so pinned
local assets stay the baseline. An empty registry is the supported no-UI
deployment. ReDoc remains E6.16 and Scalar E6.17; see ADR 0033.

E6.13 adds one internal compiled route layer for already-produced HTTP
surfaces. A schema, documentation page or future Explorer shell supplies a
stable logical name, an explicit static path, its media type, complete bytes
and optional safe headers; the layer does not know how any artifact was
generated. Compilation sorts declarations, rejects duplicate names and paths,
and reserves each surface path against every capability method so shadowing
and `405` behavior cannot depend on dispatcher order. At runtime `GET` serves
the immutable response, `HEAD` preserves its headers without body bytes,
other methods receive `405` with `Allow: GET, HEAD`, and unmatched exchanges
delegate unchanged to capability dispatch. No default route or public
configuration syntax is selected here, omission is not authorization, and UI
assets remain separate work; see ADR 0034.

E6.14 adds an immutable internal publication plan without a global boolean
bag. Schema, each documentation UI and Explorer are selected by supplying
their own typed configuration; absence means disabled, and no environment
silently changes that choice. Each UI owns its own try-it state, which defaults
off. A selected UI receives the configured schema URL only when that endpoint
is actually present; otherwise it receives the already-filtered serialized
document directly. Exactly one source is required. Explorer alone has no
OpenAPI dependency, an unused OpenAPI artifact publishes nothing, and all
selected paths pass through the E6.13 collision boundary before any provider
renders. The plan remains internal and does not implement provider HTML, CSP,
assets, visibility or authorization; see ADR 0035.

E6.15 adds internal local and CDN Swagger UI providers pinned to 5.32.14. The
local production baseline serves the verified Apache-2.0 bundle and stylesheet
from the application origin; runtime size and SHA-256 checks protect the
vendored bytes. The separately named CDN variant uses exact `unpkg.com` URLs
and SRI and remains unavailable until remote assets are explicitly permitted.
Both modes use a local initializer rather than inline JavaScript, disable the
online validator, URL configuration, credential persistence and credentialed
fetches, and leave try-it off unless this UI explicitly enables it. The
provider truthfully lists the OpenAPI 3.2 features deferred upstream; it claims
basic 3.2.0 rendering, not complete conformance. Provider composition and the
final emitted CSP remain internal follow-up work; see ADR 0036.

The design baseline is ASGI 3.0 and the HTTP/WebSocket sub-specification 2.5:

- https://asgi.readthedocs.io/en/latest/specs/main.html
- https://asgi.readthedocs.io/en/latest/specs/www.html

This is not yet a public HTTP composition API or a complete ASGI/HTTP
conformance claim. Additional documentation providers, browser integration and
Explorer remain separate roadmap work; see RFC 0003, ADR 0018, EPIC 6 and EPIC
8.

- Import package: `agnara_http`
- Depends on: `agnara-core`
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.
