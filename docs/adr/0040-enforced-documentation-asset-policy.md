# ADR 0040 — Enforced Documentation Asset Policy

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #157

## Context

ADRs 0018 and 0033 made pinned same-origin assets the production baseline,
but the original executable boundary reduced remote delivery to a boolean. A
true value accepted every HTTPS origin returned by a provider and trusted its
HTML to contain the promised exact version, integrity metadata and CORS mode.
The CSP declaration, rendered elements and deployment permission could drift
independently.

That is too coarse for executable browser code. HTTPS authenticates the
server, not immutable content. The W3C Subresource Integrity specification
requires integrity-protected cross-origin resources to use CORS, while CSP
host sources can grant an entire origin. The framework therefore needs to
prove the correspondence among the exact resource, its hash, its HTML
attributes, its CSP privilege and the deployment's decision before returning
the page.

## Decision

Pinned local assets and the no-UI deployment remain zero-configuration paths.
Remote delivery is represented by immutable per-page `_RemoteAsset` values,
each containing:

- an exact HTTPS URL without credentials, query or fragment;
- an exact semantic version that must occur in the URL path;
- one syntactically valid SHA-384 SRI digest;
- `crossorigin="anonymous"`.

At render time the provider-independent registry parses external `script` and
stylesheet references. Every remote URL must appear exactly once in HTML and
exactly once in the declarations. Its `integrity` and `crossorigin`
attributes must match the declaration. Undeclared, unused or duplicated
resources fail as provider definition errors.

The set of origins derived from those assets must exactly equal the page's
CSP external origins. Origins are canonical, sorted and unique HTTPS origins:
paths, credentials, query strings, fragments, mixed-case spellings and the
redundant default port are rejected. The deployment supplies a frozenset of
the exact origins it accepts. Any required origin outside that allowlist makes
the provider unavailable; a boolean cannot grant future provider origins.

Swagger UI 5.32.14, ReDoc 2.5.3 and Scalar 1.67.0 declare their existing
exact-version CDN resources through this value. Their pinned local variants
declare no remote resources and require no permission.

Repository-wide tests verify each vendored provider manifest, asset byte
length, SHA-256, SRI presence and shipped license, and verify that the wheel
packages the complete `agnara_http` resource tree while retaining only
`agnara` as a runtime dependency. Release verification additionally builds
and inspects the actual wheel.

## Consequences

- A newly introduced CDN origin is denied until the application names that
  precise origin.
- Provider HTML, SRI metadata and CSP cannot silently disagree.
- Mutable aliases and query-selected CDN variants cannot satisfy the
  declaration contract.
- The policy validates metadata and correspondence; it does not claim that a
  CDN currently serves the expected bytes. Browser SRI performs that check at
  fetch time, and release acquisition evidence remains responsible for the
  recorded digest.
- Local assets remain the availability and privacy baseline and add no UI
  package dependency.
- The provider contract remains internal; this decision does not select a
  public composition API or an unconditional documentation default.

## Guardrails

- Core imports no documentation, HTML, CSP or browser implementation.
- Remote scripts and styles require exact URL, SHA-384 SRI, anonymous CORS,
  matching CSP and an exact-origin deployment allowlist.
- CSP origins grant hosts only to script and style directives; they do not
  enlarge `connect-src`.
- Same-origin asset paths may not be protocol-relative or traverse their
  resource root.
- Vendored assets, manifests and upstream licenses must all appear in the
  built wheel and remain hash-consistent.
- No-UI and pinned local modes must never require network permission.

## Primary evidence

- https://www.w3.org/TR/SRI/
- https://www.w3.org/TR/CSP3/
- `packages/agnara-http/src/agnara_http/_documentation.py`
- `tests/http/test_documentation_contract.py`
- `tests/http/test_documentation_assets.py`
