# ADR 0090 — Public HTTP Documentation Composition

- Status: Proposed
- Date: 2026-09-13
- Tracking: GitHub Issue #394
- Related: ADR 0018, ADR 0035–0040, ADR 0049, ADR 0071

## Context

`agnara-http` already has generated OpenAPI 3.2, pinned local and CDN
documentation providers, CSP/SRI enforcement, static-surface collision checks,
and a separate authorized Explorer. Until this decision, these pieces could
only be assembled through underscore-prefixed modules and test-only hosts.

The boundary must retain four distinctions: generating an OpenAPI artifact is
not serving it; serving a schema is not serving HTML; an OpenAPI UI is not
Agnara Explorer; seeing metadata is not authority to invoke a capability.

## Decision

`agnara_http` owns public documentation composition. It exports these
provisional value types from `agnara_http.composition` and the package root:

| Type | Responsibility |
| --- | --- |
| `HttpDocumentation` | Independent schema/UI selection; its default is local Swagger UI at `/docs` and schema at `/openapi.json`. |
| `OpenApiSchema` | One configurable OpenAPI publication path. |
| `SwaggerUI`, `Scalar`, `ReDoc` | Built-in renderer selections, each with a path and its own `try_it` choice where the renderer supports it. |
| `DocumentationAssets` | Local verified assets, or an exact-origin permission for a built-in provider's fixed CDN resources. |
| `HttpExplorer` | Separate Explorer path, snapshot, visibility policy and principal resolver. |

`Http.compile(..., openapi=OpenApiInfo(...), documentation=HttpDocumentation())`
is the normal development profile. It produces `GET /openapi.json` and local
Swagger UI at `GET /docs`; `try_it` is false, credential persistence is false,
and no remote network origin is used.

Every selection is independent. `schema=None` gives a selected UI the
serialized generated document directly; it does not publish `/openapi.json`.
A schema without a UI is valid. Omitting `documentation` leaves the existing
generated-but-unserved `HttpApplication.openapi()` behaviour intact.
`openapi_path` remains the legacy schema-only spelling and is intentionally
refused together with `documentation` so one compile has one publication
configuration.

Built-in providers remain replaceable internally, but the provider protocol is
not public in 1.0. Applications select the reviewed built-ins rather than
receiving the route registry, compiled plans, capability definitions, or an
arbitrary JavaScript configuration dictionary. A future provider requires a
separate public-extension decision, without changing this selection API.

Swagger UI and Scalar accept the canonical 3.2 document according to their
pinned compatibility declarations. ReDoc 2.5.3 declares only 3.1 support;
selecting it with Agnara's 3.2 document fails at compilation with its explicit
diagnostic. The document is never transformed or downgraded for a renderer.

The compiled documentation routes reserve pages and every local asset through
the existing static-surface collision boundary. They provide GET, HEAD and
405/`Allow: GET, HEAD` semantics. Documentation pages and their initializer
assets render with the ASGI `root_path` prefix at request time, while the
generated artifact and route selection remain fixed at startup.

`HttpExplorer` deliberately does not consume OpenAPI. It requires a caller
supplied `IntrospectionSnapshot`, `DiscoveryVisibility`, principal resolver and
either a challenge for authenticated viewing or explicit anonymous opt-in.
Explorer owns a subtree, which cannot shadow capability or documentation
surfaces. The authorized JSON discovery endpoint remains internal: its public
configuration is a separate non-HTML API decision.

## Security consequences

- Local vendored assets remain the default and are hash-checked before use.
- CDN mode needs `DocumentationAssets.remote()` with exact HTTPS origins; the
  built-in provider retains exact version URLs, SRI and CSP declarations.
- Documentation receives exactly one OpenAPI source, never compiled runtime
  objects or unfiltered introspection.
- `try_it` is opt-in per UI; it does not bypass normal HTTP policy,
  authentication or confirmation boundaries.
- Explorer visibility and invocation authorization remain separate decisions.

## Alternatives rejected

- A flag bag (`swagger=True`, `try_it=True`, `explorer=True`): it obscures
  independent publication and security decisions.
- FastAPI/Starlette mounting or a sidecar UI server: it duplicates routing and
  breaks the one compiled Agnara surface.
- Publishing the internal provider protocol: its current shape is deliberately
  constrained around implementation details and needs a separate extension
  lifecycle.
- Rewriting OpenAPI 3.2 to 3.1 for ReDoc: it would make the browser and schema
  endpoints disagree about the contract.

## Verification

Public-composition tests cover the default local profile, embedded schema,
explicit try-it, optional Scalar, explicit ReDoc refusal, CDN origin denial,
collision detection, GET/HEAD/405 and mounted paths. Existing asset, wheel,
CSP and browser suites continue to verify the pinned providers.
