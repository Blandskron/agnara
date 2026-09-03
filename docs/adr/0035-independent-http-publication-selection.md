# ADR 0035 — Independent HTTP Publication Selection

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #147

## Context

RFC 0003 requires OpenAPI schema serving, each human UI, Agnara Explorer and
interactive try-it to be independently configurable. A single group of
booleans such as `openapi`, `docs`, `redoc` and `explorer` looks convenient,
but it hides dependencies and scales poorly as providers change.

E6.13 introduced an explicit static surface-route layer, while E6.12 defined
the provider request. The latter always required a `document_url`, even when
serialized document bytes were also supplied. A UI with the schema endpoint
disabled would therefore receive a URL that the application did not serve.

## Decision

The internal publication configuration uses presence, not a global boolean
bag. Schema, each documentation UI and Explorer have separate typed
configuration values. `None` or omission means disabled. Paths remain
explicit and have no environment-dependent defaults.

An immutable OpenAPI artifact pairs already-filtered serialized bytes with
the exact version declared inside those bytes. Schema serving and
documentation UIs require this artifact. Explorer does not: its future data
model is protocol-neutral introspection, not OpenAPI.

Each documentation UI declaration names one provider and owns its route,
asset base URL, title and try-it state. Try-it defaults off and cannot turn on
another provider. Duplicate provider selections are rejected because one
provider name identifies one configured UI in an application.

Provider requests carry exactly one document source. When the schema route is
selected, a UI receives that same-origin URL and no document bytes. When the
schema route is absent, it receives serialized bytes and no URL. Supplying
both or neither is a definition error.

Compilation sorts UI declarations, creates only selected static surfaces and
provider render requests, and sends all selected route reservations through
the E6.13 collision boundary. It does not render providers. Provider HTML,
CSP and assets remain downstream provider and asset-policy work.

## Consequences

- Schema-only, Explorer-only, schema plus any subset of UIs, and UI without a
  public schema endpoint are truthful configurations.
- All HTML may be absent while the machine-readable schema remains served.
- OpenAPI generation itself remains independent: an artifact with no selected
  HTTP surface publishes nothing.
- Adding a provider does not add another top-level boolean or change another
  provider's try-it state.
- The configuration remains internal until the complete HTTP composition API
  is reviewed; this ADR stabilizes semantics, not public spelling.

## Guardrails

- No configuration choice grants discovery visibility or invocation
  authorization.
- Inputs are already filtered before they enter the plan.
- Explorer never derives its data from OpenAPI.
- Schema and UI routes cannot exist without a self-consistent OpenAPI
  artifact.
- Provider rendering, CSP construction and asset serving are not performed by
  the selection plan.
- No UI dependency enters `agnara-http` or `agnara-core`.
