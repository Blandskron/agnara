# ADR 0037 — Pinned ReDoc Providers and an Honest 3.2 Boundary

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #151

## Context

ADR 0018 chose ReDoc Community Edition as the readable-reference baseline for
an implementation spike, while ADR 0033 requires every provider to name exact
tested OpenAPI versions and fail rather than rewrite the canonical document.
E6.16 must implement that spike under the same local-asset, compatibility and
security rules as Swagger UI.

ReDoc CE 2.5.3 is the latest 2.x release as of this decision. Its release notes
say it prevents a crash for OpenAPI 3.2, but the project README still claims
support only for OpenAPI 3.1, 3.0 and Swagger 2.0, and its 3.2 support issues
remain open. Preventing a crash is not rendering compatibility. Agnara's
canonical document remains OpenAPI 3.2.0, so declaring ReDoc compatible would
be false and downgrading the document would violate ADR 0018.

ReDoc CE also has no interactive try-it console. That feature belongs to the
hosted commercial product and cannot be simulated by silently ignoring the
provider request.

The standalone bundle injects runtime styles and creates its search worker
from a `blob:` object URL. The documentation CSP declaration represented
inline styles and remote origins but could not express that worker privilege.

## Decision

`agnara-http` contains two internal providers backed by ReDoc CE 2.5.3:

- `redoc` serves the pinned standalone bundle from the application origin;
- `redoc-cdn` references the exact version at `cdn.redoc.ly` with SHA-384
  Subresource Integrity.

The providers declare only OpenAPI 3.1.0 as tested. When Agnara supplies its
canonical 3.2.0 artifact, the registry reports the provider unavailable before
rendering. The document is not relabelled, projected down or stripped of 3.2
features. A request with try-it enabled is also unavailable with a diagnostic
that ReDoc CE has no console.

The local bundle comes from the official `redoc@2.5.3` npm tarball obtained
with `npm pack --ignore-scripts`. Agnara does not install its 21 package
dependencies or run its `prepare` hook. The upstream MIT license, bundle
license and a machine-readable manifest ship alongside the asset. Runtime
loading verifies its exact size and SHA-256 hash.

Each render emits a same-origin `redoc-initializer.js` asset instead of inline
JavaScript. It passes either the same-origin schema URL or strict UTF-8 JSON
bytes received from the filtered publication plan. Inline JSON is reconstructed
with `JSON.parse`, and the title is HTML-escaped. ReDoc receives
`untrustedSpec: true`, enabling its sanitization path, and
`hideDownloadButtons: true`, keeping UI presentation independent from the
separately configured machine-readable schema surface. Hiding that button is
not authorization.

The CSP declaration gains `blob_worker: bool`. ReDoc sets it together with
`inline_style`; it does not request inline JavaScript. A blob worker is an
explicit browser privilege but not a remote origin, so it does not satisfy or
bypass the registry's remote-assets opt-in. Local ReDoc declares no network
origin. The CDN provider declares only `https://cdn.redoc.ly` and remains
unavailable until the deployment permits remote assets.

The upstream bundle contains a Redocly footer-logo URL. It falls back to text
when the image fails. Local mode deliberately does not authorize that origin,
so the response CSP blocks the image rather than turning branding into a
hidden network dependency. The inspected bundle contains no Google Fonts
origin. E6.18 must exercise both facts in a real browser before the final CSP
integration is considered complete.

## Consequences

- ReDoc is implemented without becoming a false OpenAPI 3.2 compatibility
  claim; it will not render Agnara's current generated document until supported
  upstream evidence exists or an explicit loss-aware compatibility projection
  is separately designed.
- Applications with an independently supplied, tested OpenAPI 3.1.0 document
  can render the provider through the same contract.
- `agnara-http` gains no Python or npm dependency and ships about 1.10 MB of
  additional raw browser assets.
- The local provider has no CDN/font dependency. The versioned CDN mode adds a
  declared availability/privacy dependency and is opt-in.
- E6.18 translated the explicit style and blob-worker requirements into a
  real-browser-tested response CSP. E6.19 can generalize the manifest/build
  policy.
- No documentation UI is selected as an unconditional default.

## Guardrails

- No ReDoc type or dependency enters `agnara-core`.
- No provider receives the registry or can reconstruct hidden exposures.
- OpenAPI 3.2 is refused, never downgraded silently.
- Try-it is refused, never ignored silently.
- Local mode declares no external origin; CDN mode pins the version and SRI
  and requires deployment permission.
- Untrusted-spec sanitization is always enabled and JavaScript is not inline.
- The worker `blob:` requirement is explicit and does not count as network
  permission.
- Vendored bytes and licensing evidence ship in the wheel and are verified.

## Primary evidence

E6.18 subsequently verified the local 3.1 provider under the emitted CSP in
Playwright 1.62.0 Chromium. The blob worker runs, remote branding and malicious
images are blocked, XSS remains inert, credential-named storage stays empty,
and keyboard/mobile smoke checks pass. The contract still refuses 3.2 before
browser delivery. See ADR 0039; this is not WCAG conformance.

- https://github.com/Redocly/redoc/releases/tag/v2.5.3
- https://github.com/Redocly/redoc
- https://github.com/Redocly/redoc/issues/2773
- https://github.com/Redocly/redoc/issues/2746
- https://redocly.com/docs/redoc/config
- https://registry.npmjs.org/redoc/-/redoc-2.5.3.tgz
