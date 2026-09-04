# RFC 0003 — HTTP Documentation and Capability Explorer

- Status: Draft
- Target: v0.1 architecture and post-v0.1 Explorer delivery
- Decision owner: Project maintainer
- Tracking: GitHub Issue #9

## Summary

Agnara will generate OpenAPI 3.2 from compiled HTTP exposures and offer
replaceable human documentation interfaces over that generated contract.
Separately, Agnara will define a protocol-neutral introspection snapshot for
machine discovery, the CLI and a future Agnara Explorer.

The architecture is:

```text
Capabilities
      ↓
HTTP Exposures
      ↓
OpenAPI 3.2
      ↓
Documentation provider boundary
      ├── Swagger UI provider
      ├── ReDoc provider
      ├── other evaluated providers
      └── no UI

Compiled project/capability introspection
      ↓
Filtered protocol-neutral snapshot
      ├── CLI text / JSON
      ├── agent discovery
      └── Agnara Explorer
```

OpenAPI is an HTTP contract. It is not the canonical capability model and
cannot represent the complete Agnara graph.

## Current state

As of 2026-08-31:

- `ARCHITECTURE.md` already assigns OpenAPI generation to `agnara-http`;
- `docs/API_DESIGN.md` already sketches `Http(openapi=True)` and
  `app.describe(format="agnara")`;
- `docs/CLI_SPEC.md` already sketches `agnara schema openapi` and
  `agnara inspect ... --json`;
- `BACKLOG.md` targets OpenAPI 3.2 and protocol-neutral introspection;
- `CapabilityDefinition` implements immutable identity, effects, risk,
  confirmation and idempotency metadata;
- `agnara-http` contains only its package boundary and docstring;
- there is no HTTP exposure registry, schema port, OpenAPI generator,
  discovery snapshot, documentation route or UI dependency yet;
- no earlier GitHub Issue or Pull Request covered this architecture.

This RFC therefore specifies boundaries and sequencing. It does not claim
that the features are implemented.

## Goals

- generate one OpenAPI document without a manually maintained parallel file;
- keep OpenAPI and every documentation UI outside `agnara-core`;
- let UI implementations be installed, replaced or removed independently;
- preserve machine-readable discovery without requiring HTML parsing;
- represent capability semantics that OpenAPI cannot express;
- make schema, UI, Explorer and interactive execution independently
  configurable;
- apply visibility, redaction and authorization before serialization;
- support deterministic export and protocol conformance testing.

## Non-goals

- making HTTP the source of capability semantics;
- representing non-HTTP capabilities as invented OpenAPI paths;
- embedding an LLM or agent reasoning engine;
- selecting a permanent third-party UI in this RFC;
- stabilizing configuration names or default routes before implementation
  spikes and API review;
- treating metadata such as `risk` or `confirmation` as authorization.

## 1. One semantic source, two projections

### OpenAPI projection

The only generated OpenAPI source is:

```text
CapabilityDefinition
+ compiled HTTP exposure
+ schema adapter output
+ explicitly publishable policy/discovery metadata
        ↓
OpenAPI 3.2 document
```

`agnara-http` owns this projection. It may consume protocol-neutral contracts
from core, but core must not import OpenAPI types or packages.

An operation exists in generated OpenAPI only when it has an enabled and
discoverable HTTP exposure. A capability exposed only through MCP, A2A,
events, tasks, CLI or direct invocation does not become a fake HTTP path.

Schema components are derived through the schema port and reused by
reference. Developers do not maintain a second schema declaration solely for
OpenAPI.

Generated documents must be deterministic for an identical compiled
application. Stable capability and exposure identifiers should drive stable
`operationId` values; the exact rule needs an implementation RFC or golden
fixtures before becoming public.

### Protocol-neutral introspection projection

The capability runtime needs a read-only, immutable snapshot representing the
compiled application. The exact Python types remain pending, but the semantic
shape includes:

```text
Project
Apps
Capabilities
Exposures
Dependencies
Policies
Effects
Risk
Idempotency
Confirmation
Schemas
Transport availability
```

Core may define neutral descriptor contracts because multiple transports and
the CLI consume them. Adapter-specific details are contributed through an
extension boundary and represented as namespaced, serializable data; core
does not import an adapter to obtain them.

The serialized snapshot is versioned independently from OpenAPI. It is not a
dump of internal Python objects, dependency instances, policy code or secrets.

## 2. Publication pipeline

Both projections use the same security-sensitive publication stages:

```text
compiled model
→ select visibility for the requested surface and viewer
→ remove private/internal entries
→ redact sensitive metadata and examples
→ project to OpenAPI or introspection representation
→ serialize
→ render optional human UI
```

Filtering after serialization is rejected because references, indexes and
derived descriptions can leak removed information.

The system must distinguish at least these decisions:

1. whether a capability is registered and executable;
2. whether it is discoverable to a given principal;
3. whether an HTTP exposure appears in OpenAPI;
4. whether a human UI is served;
5. whether interactive execution is enabled in that UI.

No one boolean may silently grant all five.

## 3. Documentation provider boundary

`agnara-http` will define the HTTP integration contract for a documentation
provider. A provider receives a local OpenAPI URL or already-filtered document
plus safe presentation configuration and returns the HTML/static asset
response needed for its UI.

Provider implementations must remain optional. `agnara-http` itself must not
acquire a required JavaScript runtime or a required UI asset dependency.

The packaging spike must compare:

- extras such as `agnara-http[swagger]` and `agnara-http[redoc]`;
- separately versioned provider distributions;
- application-supplied providers implementing the same contract.

Extras may be convenience installation aliases, but they must not turn the
provider into core semantics. The final packaging choice requires evidence
for wheel size, update cadence, license notices, dependency scanning and
asset provenance.

### Asset policy

The secure baseline is version-pinned, locally served assets with integrity
recorded in the release/build process. CDN loading is explicit opt-in.

An opt-in CDN configuration must pin an exact version, document the allowed
origins and CSP changes, and use subresource integrity when the distribution
supports stable hashes. A mutable `latest` CDN URL is not an acceptable
production default.

ADR 0040 makes this policy executable. Every external script and stylesheet
has immutable exact-version URL, SHA-384 SRI and anonymous-CORS metadata. The
registry verifies that rendered HTML, declarations and CSP correspond exactly
and accepts a set of canonical allowed origins rather than a boolean. Local
assets and no UI require no network permission.

The no-UI provider remains valid. OpenAPI generation cannot require a browser
interface.

## 4. UI research and selection

The detailed, dated comparison is maintained in
`docs/REFERENCE_RESEARCH.md`. The 2026-08-31 result is:

- Swagger UI is the compatibility-oriented baseline and currently has basic,
  not complete, OpenAPI 3.2 rendering;
- ReDoc Community Edition is strong for readable reference documentation but
  its documented support line remains OpenAPI 3.1 and it has no community
  try-it console;
- Scalar is the leading modern UX candidate and its parser supports OpenAPI
  3.2, but end-to-end API Reference 3.2 work is still tracked as incomplete;
- Stoplight Elements remains embeddable and actively patched, but carries a
  larger React-oriented dependency surface and no evidenced 3.2 claim;
- RapiDoc is an embeddable Web Component with a small integration surface,
  but its npm release cadence and WCAG roadmap make it a weaker default
  candidate.

No provider is selected as an unconditional default. Swagger UI, ReDoc and
Scalar should receive implementation spikes against the same conformance,
security, bundle and accessibility fixtures. Adding RapiDoc or Elements later
must require no change to capability runtime semantics.

E6.15 completed the Swagger UI integration spike with version 5.32.14. ADR
0036 records the local-asset baseline, distinct opt-in CDN provider, integrity
evidence, secure initializer defaults and the exact OpenAPI 3.2 features still
deferred upstream. This is compatibility evidence for one provider version,
not selection of an unconditional default or a claim of complete 3.2 support.

E6.16 completed the ReDoc CE spike with version 2.5.3. ADR 0037 records its
local and opt-in CDN assets, sanitization and CSP needs. ReDoc's upstream 3.2
work remains incomplete and CE has no try-it console, so the provider refuses
both requests explicitly. It never downgrades the canonical document or
pretends that a read-only reference interface is interactive.

E6.17 completed the Scalar API Reference spike with version 1.67.0. ADR 0038
records its self-contained pinned bundle, exact-version opt-in CDN mode,
explicit telemetry/plugin/agent/font boundaries and partial OpenAPI 3.2 and
accessibility evidence. Scalar remains the leading modern-UX candidate, but
the upstream end-to-end 3.2 tracker and active ARIA defects mean no provider is
selected as an unconditional default before E6.18 runs comparable browser
fixtures.

E6.18 now runs those comparable fixtures in a required Playwright
1.62.0/Chromium CI job. ADR 0039 records real-browser rendering through the
compiled ASGI surface boundary, exact CSP/security headers, blocked XSS and
undeclared origins, try-it and storage state, an unpublished same-origin OAuth
redirect boundary, keyboard focus and a 390 by 844 responsive smoke viewport.
The evidence is intentionally narrower than WCAG or complete OpenAPI
conformance. Scalar's active ARIA gaps, ReDoc's 3.2 incompatibility and the
provisional public composition API still prevent an unconditional default.

E6.19 enforces the common asset boundary independently of provider. ADR 0040
records exact remote-resource metadata, HTML/SRI/CORS correspondence,
canonical CSP origins, deployment origin allowlists and repository-wide
vendored-resource packaging evidence. This closes the asset-policy work
without selecting a UI default or making a CDN part of the baseline.

The canonical generated contract remains OpenAPI 3.2 even when a provider
lags behind it. A provider must fail with a clear compatibility diagnostic or
remain unavailable; it must not silently change only the `openapi` version or
drop 3.2 fields. Any future loss-aware 3.1 compatibility projection is a
separate, explicitly requested artifact with a machine-readable loss report
and requires its own ADR.

## 5. Routes and configuration

The target experience remains recognizable:

```text
/openapi.json
/docs
/redoc
/agnara
```

These paths are provisional. Implementations must support explicit path
configuration, disabling and collision detection before any default is
declared stable.

This remains a design sketch, not committed public syntax:

```python
Http(
    openapi=True,
    docs=True,
    redoc=False,
    explorer=True,
)
```

The reviewed API should separate schema configuration, documentation
providers and Explorer configuration rather than accumulating ambiguous
booleans. In particular, these must be independently possible:

- no schema and no UI;
- schema only;
- schema plus one or more UIs;
- protocol-neutral discovery without an HTTP UI;
- Explorer served by HTTP but with a restricted snapshot;
- all HTML UIs disabled while machine-readable contracts remain available.

Generated production scaffolds may choose safer production settings than
development settings, but the runtime must not guess an environment and
silently publish private surfaces.

## 6. Agnara Explorer

Agnara Explorer is not another OpenAPI skin. It visualizes the richer
protocol-neutral snapshot.

Conceptual detail view:

```text
payments.refund

Capability
  Input: RefundCommand
  Output: RefundReceipt

Security
  Scope: payments:refund
  Risk: high
  Effect: financial-write
  Confirmation: policy

Exposures
  HTTP  POST /refunds
  MCP   refund_payment
  A2A   refund_payment

Dependencies
  PaymentRepository
  AuditPublisher
```

An initial Explorer may be delivered over HTTP, but its data source cannot be
the OpenAPI document. A non-HTTP host or a future desktop/terminal interface
must be able to consume the same filtered snapshot.

Explorer requirements include:

- project/app/capability navigation;
- exposure and transport availability views;
- dependency graph views without runtime object values;
- schema views;
- policy/effect/risk/idempotency/confirmation views only when publishable;
- human-readable empty, loading, denied and partial-visibility states;
- accessible keyboard and screen-reader navigation;
- responsive/mobile behavior;
- deep links based on stable logical identifiers;
- a machine-readable endpoint or CLI export that does not require the UI.

## 7. CLI and agent-first discovery

The canonical candidates are:

```bash
agnara schema openapi
agnara inspect
agnara inspect payments
agnara inspect payments --json
```

`agnara schema openapi` exports the same OpenAPI projection that the HTTP
schema endpoint serves. `agnara inspect ... --json` exports the same
versioned introspection snapshot consumed by Explorer, subject to an
explicit offline/publication policy.

`agnara docs` is deferred. It is justified only if it adds Agnara-specific
value, such as starting a documented development composition and opening the
configured UI. It must not duplicate `agnara dev` or hide production
configuration.

Machine output requires stable versioning, deterministic ordering, defined
exit codes and no ANSI decoration. Human text output may evolve more freely.

## 8. Security and privacy requirements

### Visibility and authorization

- private/internal capabilities are not published automatically;
- schema and introspection endpoints can have independent authorization;
- viewer-specific documents are filtered before projection and use correct
  cache controls and `Vary` semantics;
- viewing a capability does not authorize invoking it;
- try-it requests traverse the normal authentication, policy and execution
  pipeline;
- dependency names, internal policy structure and transport configuration
  are publishable only through an explicit safe representation.

### Sensitive schemas and examples

- secret values, credentials and runtime configuration never become examples
  or defaults;
- descriptions and examples are treated as untrusted content at the UI
  boundary;
- external `$ref` resolution is disabled by default or constrained by an
  explicit allowlist and resource limits;
- redaction happens before reference/component assembly so hidden material is
  unreachable from the published document.

### Try-it and authentication

- interactive execution can be disabled independently from documentation;
- high-risk and side-effecting operations must remain subject to normal
  confirmation and policy behavior;
- OAuth browser flows use public-client patterns such as Authorization Code
  with PKCE where applicable;
- client secrets are never embedded in generated HTML, JavaScript or checked
  configuration;
- redirect origins and allowed servers are explicit;
- credentials are not persisted by default.

### Browser security

- locally served, pinned assets are preferred over external CDNs;
- generated pages sanitize rendered Markdown/HTML and untrusted links;
- providers must document their CSP needs, including inline styles/scripts,
  nonces, workers, fonts, network connections and frames;
- default responses define an appropriate `Content-Security-Policy`,
  `X-Content-Type-Options`, `Referrer-Policy` and framing policy;
- personalized or nonced HTML is not publicly cached;
- provider versions and assets participate in dependency/security updates.

## 9. Conformance and quality gates

OpenAPI work is not complete when one sample renders.

Required evidence includes:

- deterministic golden documents;
- OpenAPI 3.2 structural validation against a pinned conformance tool or
  official schema where available;
- schema reference/deduplication tests;
- path, parameter, request, response, error and security-scheme fixtures;
- visibility/redaction fixtures;
- explicit unsupported-feature tests;
- provider contract tests that run without each optional UI installed;
- browser tests for route configuration, CSP, disabled UIs, try-it state,
  authentication flow integration and XSS payloads;
- accessibility and responsive smoke tests for every supported provider;
- wheel and browser-asset size budgets recorded by provider;
- architecture tests proving core has no OpenAPI/UI dependency.

Claims of full OpenAPI 3.2 compatibility require these tests and release
documentation, not only a version string in generated JSON.

## 10. Delivery sequence

Each item should be one reviewable Issue/branch/PR unless its Issue proves two
steps technically inseparable:

1. protocol-neutral introspection snapshot contract;
2. schema port and JSON Schema export;
3. compiled HTTP exposure model;
4. OpenAPI 3.2 projection and deterministic export;
5. OpenAPI conformance and security fixtures;
6. documentation provider contract and secure asset policy;
7. Swagger UI provider spike/integration;
8. ReDoc provider spike/integration;
9. Scalar comparison spike and selection review;
10. configurable routes, disabling and collision handling;
11. discovery visibility/redaction/authorization controls;
12. CLI `schema openapi` export;
13. CLI `inspect` text and versioned JSON;
14. Agnara Explorer read-only MVP;
15. browser, CSP, XSS, accessibility and mobile tests.

## Rejected alternatives

### Put OpenAPI or UI types in core

Rejected because it violates the transport-neutral dependency direction.

### Maintain a handwritten OpenAPI file beside capabilities

Rejected because it creates two semantic sources and inevitable drift.

### Use OpenAPI as the complete capability manifest

Rejected because OpenAPI cannot faithfully model non-HTTP exposures, project
apps, dependency graphs or all policy/effect semantics.

### Ship a mutable CDN `latest` UI by default

Rejected because it makes builds non-reproducible and expands the production
supply-chain and CSP boundary without explicit consent.

### Treat hidden navigation as access control

Rejected because an omitted UI button or operation is not authorization.

## Open questions

1. Exact Python types and versioning rules for the introspection snapshot.
2. Exact visibility declaration and discovery-policy interface.
3. Exact configuration objects and route defaults.
4. Provider packaging: extras, separate distributions or both.
5. Which OpenAPI 3.2 validator/conformance fixtures are authoritative.
6. Whether the first Explorer is server-rendered, a bundled static app or a
   separate frontend artifact.
7. Whether viewer-specific OpenAPI documents are cached and, if so, by what
   safe key.
