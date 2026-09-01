# ADR 0018 — Replaceable Documentation Providers over Generated Contracts

- Status: Proposed
- Date: 2026-08-31
- Tracking: GitHub Issue #9

## Context

Agnara needs familiar HTTP API documentation, modern interactive exploration
and richer capability discovery. These are related experiences, but they do
not share one complete semantic format:

- OpenAPI describes HTTP APIs;
- Agnara introspection describes projects, apps, capabilities, every exposure,
  dependencies and publishable policy/effect metadata;
- Swagger UI, ReDoc, Scalar and similar products are replaceable browser
  renderers with different compatibility and security tradeoffs.

Making a particular UI or OpenAPI itself part of core would invert Agnara's
capability-first architecture.

The dated research in `docs/REFERENCE_RESEARCH.md` also shows that OpenAPI 3.2
support is uneven across current UI products. Selecting one implementation as
an architectural source of truth would couple Agnara to its release cadence
and unsupported features.

## Decision

1. `agnara-http` owns the projection from compiled HTTP exposures to generated
   OpenAPI 3.2.
2. Developers do not maintain a parallel OpenAPI schema for generated
   exposures.
3. Human OpenAPI UIs sit behind an optional documentation-provider boundary.
   No UI implementation is a required dependency of `agnara-core` or
   `agnara-http`.
4. The secure production baseline is pinned, self-hosted assets. CDN assets
   require explicit opt-in, exact versioning and documented CSP/integrity
   implications.
5. Agnara Explorer consumes a filtered, protocol-neutral introspection
   snapshot. It does not reconstruct capabilities from OpenAPI.
6. Human UIs and machine-readable contracts are separate surfaces. Either can
   be disabled without implying the other.
7. Visibility, redaction and authorization are applied before OpenAPI or
   introspection serialization. UI hiding is never an authorization control.
8. Swagger UI is the compatibility baseline, ReDoc is the readable-reference
   baseline and Scalar is the leading modern-UX candidate for initial spikes.
   None is designated the permanent or unconditional default until the same
   OpenAPI 3.2, CSP, accessibility, size and security gates are run.
9. Exact routes, configuration syntax and provider packaging remain
   provisional until the implementation spikes update `docs/API_DESIGN.md`.

## Why not decide an extra now?

`agnara-http[swagger]` and similar extras are plausible convenience syntax,
but an extra is a packaging mechanism, not the architectural boundary. The
project does not yet have measured wheels, pinned asset artifacts or a
provider interface. Choosing the extra first would let package layout dictate
the design.

The provider spike will decide whether extras install separately versioned
provider packages, whether providers remain application-supplied, or whether
both forms are justified.

## Consequences

Positive:

- core remains transport-neutral;
- one generated OpenAPI contract can feed multiple UIs and CLI export;
- a UI security or maintenance problem does not require capability-runtime
  changes;
- Explorer can include MCP, A2A, event, task and direct availability;
- deployments can expose schema without HTML or disable all documentation;
- agents can discover capabilities without parsing a browser page.

Negative:

- Agnara must maintain two versioned projections: OpenAPI and its own
  introspection snapshot;
- provider integrations require browser, asset, CSP and accessibility tests;
- complete OpenAPI 3.2 compatibility depends partly on external tooling whose
  support is still evolving;
- viewer-specific discovery complicates caching and requires careful
  publication policy design.

## Guardrails

- core architecture tests reject OpenAPI/UI imports and dependencies;
- providers accept only an already-filtered document or snapshot;
- no provider may require a network CDN at runtime by default;
- no provider may silently relabel or downgrade the canonical OpenAPI 3.2
  document to accommodate unsupported renderer features;
- no provider enables try-it or credential persistence implicitly;
- capability descriptions, schemas and examples are untrusted UI input;
- a provider compatibility claim names tested versions and unsupported
  features;
- implementation follows the small Issues listed in RFC 0003 and
  `BACKLOG.md`.

## Revisit when

- one provider demonstrates materially better conformance, accessibility,
  security and maintenance across supported releases;
- Python packaging evidence favors extras or separate provider distributions;
- OpenAPI 3.2 UI support is mature enough to select a default confidently;
- a standard emerges that can represent the Agnara capability graph without
  losing its transport-neutral semantics.
