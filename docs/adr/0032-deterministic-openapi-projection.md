# ADR 0032 — Deterministic OpenAPI 3.2 Projection

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #135

## Context

The HTTP adapter has an immutable registry in which each route resolves to a
compiled capability plan and compiled request binding. Core's schema port has
already compiled every capability input into a transport-neutral `TypeSchema`.
E6.7 needs to project that state into OpenAPI without making OpenAPI a second
authoring surface or adding protocol vocabulary to core.

Publication is security-sensitive. Registration makes an operation executable;
it does not make the operation, its capability identifier, description, tags,
or schemas safe to publish. The later viewer-specific authorization model is
not designed yet, so a safe initial projection cannot infer visibility.

The runtime also does not yet compile or validate output schemas. Reflecting on
a handler again inside the HTTP adapter would violate compile-once and could
select a different schema adapter from the one that compiled the plan.

## Decision

`agnara-http` owns a dependency-free internal OpenAPI 3.2.0 projector. It
accepts the same frozen route registry used by dispatch plus validated document
`info`. It consumes input JSON Schemas only through the plan's compiled schema
port values.

An exposure contributes to OpenAPI only when it carries an explicit
`_OpenAPIPublication`. Filtering happens before path validation, identifier
creation, metadata access, or schema assembly. Capability descriptions require
a second explicit `publish_description` decision. Scopes, policies, effects,
risk, confirmation metadata, dependencies, examples, and runtime values are
never published by this projection.

Operations use a stable identifier composed from capability identity, normalized
HTTP method and path template. The projection supports only the operation fields
OpenAPI 3.2 defines: `GET`, `PUT`, `POST`, `DELETE`, `OPTIONS`, `HEAD`, `PATCH`,
`TRACE`, and `QUERY`. A published custom method fails projection rather than
being dropped or represented through an invented extension.

Path, query, and header parameters plus JSON request bodies come from compiled
bindings and compiled input schemas. Path parameters are always required;
other parameters and request bodies use the capability plan's required-input
set. `Accept`, `Content-Type`, and `Authorization` header bindings fail
projection because OpenAPI ignores those names as ordinary Header Parameters;
security schemes and content negotiation require later explicit designs.

The response contract describes only behavior the current adapter implements:

- `200` with an unconstrained JSON value, because no output schema is compiled;
- `204` for a successful result with no value;
- a default `application/problem+json` response referencing one reusable
  component with the common RFC 9457 wire members;
- no response body content for `HEAD`.

It does not claim that every listed response occurs for every capability or
that every possible status is enumerated. Output schema compilation and
per-operation response refinement require their own runtime decision.

The document identifies OpenAPI `3.2.0` and the OAS dialect based on JSON Schema
Draft 2020-12. Serialization is compact, sorted-key, UTF-8 JSON and rejects
cycles, non-string object keys, non-finite numbers, and non-JSON schema values.

## Consequences

- One compiled HTTP application can produce a byte-stable OpenAPI document
  without a UI package or third-party OpenAPI model.
- Hidden exposures contribute no derived or copied material to the document.
- Request schemas cannot drift from the plan used for invocation.
- The generic `200` schema is intentionally less precise than the Python return
  annotation until output schemas become compiled runtime state.
- OpenAPI serving routes, CLI export, provider UIs, viewer-specific policy,
  security schemes, schema deduplication, and conformance fixtures remain
  independent follow-up work.

## Guardrails

- No OpenAPI type, version, status, media type, or UI dependency enters core.
- No handwritten parallel path or schema document is accepted as generator
  input.
- Publication filtering precedes all projection and serialization work.
- Unrepresentable published methods, paths, headers, or schema values fail
  explicitly.
- Identical compiled input and document metadata produce identical bytes.
- OpenAPI 3.2 conformance is not claimed until E6.11 supplies pinned structural
  and external validation evidence.
