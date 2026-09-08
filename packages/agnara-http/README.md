# agnara-http

HTTP/ASGI exposure adapter. Owns routing, request decoding, response encoding, RFC 9457 mapping, OpenAPI generation and the authorized discovery endpoint.

## Status

`0.1.0a4` exposes the seven-name public composition API described in
`docs/HTTP_COMPOSITION.md`, including path, query, header, JSON, cookie, form
and upload bindings. Documentation providers, Explorer and the discovery
endpoint are implemented internally but are not yet reachable from that public
composition surface.

This distribution is built and versioned with the synchronized workspace set.
Which versions exist on an index is answered by its PyPI project page, not by
this file: a README ships inside the artifact and cannot describe the state of
a publication that happens after it is built.

OpenAPI 3.2 is projected from compiled HTTP exposures and shared capability
schemas. Optional browser documentation providers consume that generated
contract; Swagger UI, ReDoc, Scalar or any other UI must remain replaceable
and must not become a dependency of `agnara-core`.

Agnara Explorer is not an OpenAPI renderer. If it is initially served through
this adapter, it consumes the filtered protocol-neutral introspection snapshot
defined by the core/application composition boundary.

## How a request is served

Everything reflective happens once, at `Http.compile()`. Route templates are
parsed and checked for collisions, capabilities are resolved, execution plans
are compiled and every binding is validated against its plan's inputs. The
result is frozen, so it needs no lock and can be shared across the workers of
one process.

A request then costs a trie lookup, a binding pass over already-classified
sources, one core invocation and one serialization:

- an ASGI 3 single-callable boundary that accepts `http` scopes, accepts
  `lifespan` only when a lifecycle is configured, and refuses any other
  protocol rather than mistaking it for a supported one;
- a per-method route trie that prefers static segments, preserves significant
  trailing slashes and reports allowed methods in registration order, so a
  mismatch is a `405` carrying `Allow` rather than a `404`;
- compiled request binding with strict percent and UTF-8 decoding,
  case-insensitive header lookup, documented scalar conversion and bounded
  body reads. It produces an invocation payload for the shared core validation
  path and never substitutes for capability schema validation;
- RFC 9457 `application/problem+json` for every failure, from one reviewed
  status table.

The media type is settled from the headers before a single body byte is read,
and a route declares one body reading — JSON, form fields or uploads — because
one request has one body.

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
documentation that is wrong. Pinned local assets stay the baseline and an
empty registry is the supported no-UI deployment. E6.19 replaces the original
coarse remote-assets gate with exact resource declarations and an exact-origin
deployment allowlist; see ADRs 0033 and 0040.

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

E6.16 adds internal local and CDN ReDoc CE providers pinned to 2.5.3. The
local variant serves a size/hash-verified MIT-licensed standalone bundle; the
CDN variant uses the byte-identical exact-version `cdn.redoc.ly` resource with
SRI and remains behind remote-asset permission. Both generate a same-origin
initializer, enable untrusted-spec sanitization, hide the download button and
declare ReDoc's runtime inline-style and blob-worker needs without enabling
inline JavaScript. ReDoc CE has no try-it console and upstream still does not
claim OpenAPI 3.2 support, so those requests become unavailable explicitly;
the canonical document is never downgraded. See ADR 0037.

E6.17 adds internal local and CDN Scalar 1.67.0 providers. E6.18 then drives
all three pinned local providers through a test-only HTTP bridge over the
compiled ASGI surface dispatcher and the exact emitted security headers.
Playwright 1.62.0 Chromium verifies rendering, CSP-blocked undeclared origins,
inert XSS payloads, disabled routes, non-persisted credential state,
same-origin unpublished OAuth redirect behavior, per-UI try-it, keyboard
entry and a 390 by 844 responsive smoke viewport. Playwright remains a
workspace development dependency, not an `agnara-http` dependency. These are
browser smoke tests rather than complete WCAG/OpenAPI conformance, so the
documentation default remains explicitly deferred; see ADRs 0038 and 0039.

E6.19 enforces the asset policy at the provider-independent registry boundary.
Each remote script or stylesheet must have an exact-version HTTPS URL, valid
SHA-384 SRI and anonymous CORS declaration; its rendered HTML attributes and
CSP origin must match exactly. Deployments permit a frozen set of canonical
origins rather than a boolean, so enabling one CDN cannot authorize a future
provider host. Local providers and the no-UI deployment need no permission.
Repository-wide tests verify the vendored manifests, hashes, licenses,
packaging tree and absence of UI runtime dependencies. See ADR 0040.

The design baseline is ASGI 3.0 and the HTTP/WebSocket sub-specification 2.5:

- https://asgi.readthedocs.io/en/latest/specs/main.html
- https://asgi.readthedocs.io/en/latest/specs/www.html

This is not a complete ASGI/HTTP, OpenAPI or WCAG conformance claim. The public
composition API is experimental; see RFC 0003, ADR 0018, ADR 0071 and ADR 0072.

- Import package: `agnara_http`
- Depends on: the exact synchronized `agnara` version
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.

## Discovery endpoint

The introspection snapshot is served through a surface that is authorized by
construction rather than by configuration. It takes a principal resolver — the
application's authentication boundary, since this package verifies no
credential — and answers `401` with a declared challenge to an unidentified
viewer unless anonymous discovery is opted into explicitly.

Filtering happens per request, before serialization, so a document is never
built for one viewer and reused for another. `public`, `s-maxage` and
`immutable` are refused at startup because a viewer-specific document must not
be shared-cacheable, `Vary` is always sent, and the default is
`private, no-store`. A resolver that raises produces a redacted `500` rather
than being read as anonymous.

The body is the same document `agnara inspect --json` produces. Seeing a
capability here authorizes nothing: invocation still runs the normal policy
pipeline. See ADR 0049.

## Agnara Explorer

A read-only, server-rendered view of the same filtered snapshot the discovery
endpoint serves, with no JavaScript, no stylesheet and no external asset. That
makes read-only structural rather than configured and lets the content security
policy be `default-src 'none'` with no exceptions.

Navigation is project → application → capability. The index lists
applications, transport availability — including transports OpenAPI cannot
describe — and every visible capability. An application page carries its
provider graph; a capability page renders each published input's JSON Schema as
nested structure rather than as escaped JSON. A capability hidden from the viewer and one that does not
exist produce the same `404`, because telling them apart would publish the
existence of something withheld.

The shell has browser accessibility and navigation smoke coverage, but remains
unreachable from public composition. See ADR 0052 and `docs/MATURITY.md`.
