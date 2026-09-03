# ADR 0034 — Compiled HTTP Surface Routes

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #145

## Context

The HTTP adapter can compile capability routes, serialize one generated
OpenAPI document and validate optional documentation providers. It could not
serve a schema, documentation page or future Explorer shell through its ASGI
entry point. Adding each surface as an unrelated dispatcher would create a
second routing truth: a documentation route could shadow a capability, and
startup order would decide which target won.

RFC 0003 deliberately leaves familiar paths such as `/openapi.json`, `/docs`
and `/agnara` provisional. It requires explicit path configuration and
collision detection before any default becomes stable. It also requires
filtering and redaction before serialization, not inside a browser renderer.

## Decision

`agnara-http` has one internal compiled surface-route layer for static HTTP
artifacts. A surface declares a stable logical name, an explicit static path,
media type, complete body bytes and optional safe response headers. The path
has no default.

The layer accepts already-produced bytes. It does not receive an OpenAPI
projector, documentation provider, capability registry, introspection
snapshot or template engine. Those producers make their own publication
decisions before handing an artifact to this transport boundary.

Compilation sorts declarations, rejects duplicate logical names, reserves
each path across every HTTP method and validates those reservations against
the immutable capability route table. A collision diagnostic therefore does
not depend on registration order. Surface paths are static: parameterized
paths belong to capabilities or to a later explicitly designed asset route,
not to one fixed response body.

The surface dispatcher is a narrow wrapper around the existing capability
dispatcher. It serves `GET`, implements the corresponding `HEAD`, returns a
RFC 9457 `405` with `Allow: GET, HEAD` for another method at a reserved
surface path, and delegates every unmatched exchange unchanged. The same
`root_path` and significant-trailing-slash rules apply to both layers.

A surface path is reserved across methods rather than only for `GET`. Split
ownership such as documentation on `GET /docs` and a capability on
`POST /docs` would otherwise make `405` depend on which dispatcher answered
first and would allow infrastructure paths to become business targets.

## Consequences

- Schema, documentation and the future Explorer can share one deterministic
  routing boundary without sharing a semantic model.
- A route collision fails at startup rather than producing shadowing at
  runtime.
- No default path, public `Http(...)` syntax or UI provider is selected here.
- E6.14 remains responsible for the reviewed public enable/disable model.
- Provider asset routes remain E6.19 work; this decision serves only complete
  artifacts supplied to it.
- Already-filtered bytes are an architectural precondition. Omitting a route
  or hiding navigation is not authorization.

## Guardrails

- No change or dependency enters `agnara-core`.
- Surface paths are explicit, absolute and static.
- `content-type` and `content-length` are owned by the response boundary.
- Additional header names are lowercase HTTP tokens; duplicate, reserved or
  control-bearing headers are rejected before startup.
- Compilation is immutable and deterministic for the same declarations.
- Unmatched scopes, receive callables and send callables reach the capability
  dispatcher unchanged.
