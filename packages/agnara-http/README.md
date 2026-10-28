# agnara-http

HTTP/ASGI projection of Agnara capabilities: explicit routing and bindings,
canonical result mapping, OpenAPI, optional documentation UIs and a filtered
read-only Explorer.

```bash
pip install "agnara-http==1.0.3"
```

Import the fourteen stable composition names from `agnara_http`. The
[public composition guide](../../docs/HTTP_COMPOSITION.md) contains a complete
application, binding syntax, authentication and lifecycle configuration.
The [API reference](../../docs/API_REFERENCE.md) lists the governed exports.
Implementation modules carry no separate public compatibility promise.

This package pins the exact synchronized `agnara` version and has no runtime
dependency on a web framework, server, schema library or sibling adapter.
The published baseline is 1.0.3; current checkout fixes are recorded under
`CHANGELOG.md` `[Unreleased]`. A checkout version string does not prove that a
fix exists in the published wheel.

## Compilation and request execution

`Http.compile()` resolves declarations against a frozen capability registry,
compiles execution plans, checks bindings and route collisions, and returns an
immutable ASGI 3 `HttpApplication`. Each compiled surface belongs to one worker
event loop. Its DI container owns provider resources; ASGI lifespan closes
singletons even when no custom application lifecycle callback is configured.
Drain requests before shutdown and keep lifespan enabled on the server.

The compiled route trie prefers static segments and preserves significant
trailing slashes. A method mismatch produces `405` with `Allow`; `HEAD` can
reuse a `GET` route while suppressing body bytes. Explicit bindings select
path, query, header, JSON body, cookie, form or upload inputs. Body reading and
multipart parsing are bounded, and duplicate scalar values are refused.
Wire materialization and schema validation run inside the shared invocation
boundary after authorization and before dependency acquisition.

The application supplies the trusted principal resolver and owns credential
verification. Policies run before handler effects. A hidden documentation
operation is still subject to invocation authorization; discovery is not an
access-control mechanism.

Complete-result execution validates an explicit `output=...` contract before
serialization. Successful values are converted to deterministic UTF-8 JSON;
`None` produces a bodyless `204`. Canonical and transport failures use reviewed
RFC 9457 `application/problem+json` mappings with redacted unexpected errors.
Output conversion is a transport boundary, not a replacement for the kernel's
declared output validation. See the
[schema guide](../../docs/SCHEMA_CONTRACTS.md).

## Streaming

`Http.sse` projects declared async-generator capabilities through a GET-only
Server-Sent Events endpoint. It delays response commitment until a first unit
or terminal outcome, validates declared output units, preserves pull-based
demand, and owns disconnect cancellation and resource cleanup. Replay,
keepalive scheduling, WebSockets and other streaming transports are outside
this contract. See the [SSE guide](../../docs/HTTP_SSE.md).

## OpenAPI, documentation and discovery

OpenAPI 3.2 is projected from compiled HTTP exposures, shared schemas and
explicit operation publication metadata. The unreleased checkout publishes
the compiled output contract as the 200 JSON response schema; omitted or
explicit `Any` stays unconstrained. None still gives bodyless 204 and HEAD has
no response content. SSE routes remain absent from OpenAPI; their stream-unit
and terminal schemas have no reviewed projection. See the
[HTTP composition guide](../../docs/HTTP_COMPOSITION.md).

`HttpDocumentation` selects independent schema and built-in UI surfaces. Its
default is pinned, self-hosted Swagger UI at `/docs` with `/openapi.json`.
Swagger UI, ReDoc and Scalar remain optional consumers of the generated
document. Providers declare tested versions and fail explicitly for unsupported
requests; selecting a renderer does not establish complete OpenAPI conformance.
Try-it is off by default. CDN resources require explicit exact-origin
permission, exact versions, integrity metadata and the corresponding CSP.

`HttpExplorer` is publicly composable and separately authorized. It reads the
filtered protocol-neutral snapshot, not OpenAPI alone. The read-only shell
uses no JavaScript, stylesheet or external asset; a hidden capability and an
absent one return the same `404`. The separate JSON discovery endpoint and
third-party provider extension remain internal.

Filtering and authorization precede publication. Human UIs and machine-readable
schema publication can be configured independently. See
[HTTP composition](../../docs/HTTP_COMPOSITION.md),
[introspection](../../docs/INTROSPECTION.md) and
[current maturity](../../docs/MATURITY.md).

## Evidence and limits

`uv run pytest tests/http tests/architecture` verifies routing, bindings,
composition, lifespan, output, discovery and boundary rules. Dedicated CI
browser jobs exercise pinned documentation renderers and Explorer; ordinary
test runs omit those browser cases unless explicitly enabled. Accessibility
and responsive smoke tests are not WCAG certification or complete protocol
conformance.

The adapter handles HTTP and lifespan, with the documented SSE projection.
It does not supply an ASGI server, credential verifier, session store, CORS,
compression, static-file middleware or WebSocket runtime. Deployment concerns
remain host-owned under ADR 0072. See
[architecture](../../ARCHITECTURE.md) for package boundaries and the
[maturity inventory](../../docs/MATURITY.md) for remaining work.
