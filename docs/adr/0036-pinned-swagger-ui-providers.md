# ADR 0036 — Pinned Swagger UI Providers

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #149

## Context

ADR 0018 made pinned, self-hosted browser assets the production baseline and
ADR 0033 defined the provider contract. E6.15 must now implement Swagger UI
without turning a mutable CDN alias, an npm install lifecycle or an optimistic
OpenAPI compatibility claim into framework behavior.

The upstream evidence is precise but bounded. Swagger UI 5.32.14 was released
on 2026-08-18. Version 5.32.0 added basic OpenAPI 3.2.0 recognition, QUERY
operations and `Info.summary`, while its implementation explicitly deferred
`$self`, `additionalOperations`, component-level `mediaTypes` and `pathItems`,
Tag Object enhancements, `querystring` parameters and streaming
`itemSchema`. The provider may therefore render Agnara's canonical 3.2.0
document, but it may not claim complete 3.2 support.

The `swagger-ui-dist` npm metadata also declares `@scarf/scarf`. Installing the
package in application environments would add an unnecessary lifecycle and
telemetry surface even though the browser only needs two static files.

## Decision

`agnara-http` contains two internal providers backed by Swagger UI 5.32.14:

- `swagger-ui` serves a vendored `swagger-ui-bundle.js` and `swagger-ui.css`
  from the application's origin;
- `swagger-ui-cdn` references those same two files through exact-version
  `unpkg.com` URLs with SHA-384 Subresource Integrity.

They are separate provider names because remote delivery is a deployment
choice, not a fallback. The registry refuses the CDN provider until the
application explicitly permits remote assets. There is no `latest` URL and a
failed CDN request never switches modes silently.

The files come from the official `swagger-ui-dist@5.32.14` npm tarball obtained
with `npm pack --ignore-scripts`; no installation script runs. The package
keeps the upstream Apache-2.0 license, notice and bundle license alongside a
machine-readable manifest recording tarball provenance, sizes, SHA-256 hashes
and SRI values. Runtime loading verifies the vendored sizes and hashes before
returning the assets.

Each render creates a same-origin `swagger-initializer.js` asset. Keeping the
initializer out of the HTML means neither mode requires inline JavaScript. It
receives exactly the filtered document source from ADR 0033: either the local
schema URL or parsed UTF-8 JSON bytes. Untrusted titles are HTML-escaped.

The initializer always sets:

- `validatorUrl: null`, preventing Swagger UI's default online validation;
- `persistAuthorization: false` and `withCredentials: false`;
- `queryConfigEnabled: false`, preventing URL parameters from overriding the
  reviewed configuration;
- `supportedSubmitMethods: []` unless this specific UI selected try-it.

When try-it is explicitly selected, the provider supplies a fixed method list
including OpenAPI 3.2 `QUERY`; this changes presentation only and does not
bypass dispatch authorization, policy or confirmation.

The provider declares inline-style support because Swagger UI emits runtime
style attributes, but it does not request inline-script permission. E6.18 will
exercise the final emitted CSP and browser behavior; E6.19 will generalize the
asset-policy build gate. This issue establishes the exact provider evidence
those later gates consume.

## Consequences

- The production provider has no runtime network dependency.
- `agnara-http` gains no Python or npm dependency and never executes Swagger
  UI installation hooks; it does ship about 1.74 MB of pinned browser assets.
- CDN users accept an availability/privacy dependency on `unpkg.com` and must
  allow that origin in CSP, but SRI prevents different bytes from executing.
- A UI without a schema route still works because its filtered document is
  embedded in a separately served initializer asset.
- Compatibility gaps remain visible through the provider contract and can be
  removed only with new versioned evidence.
- The implementation remains internal until the complete HTTP composition API
  and route-serving integration are reviewed.

## Guardrails

- No Swagger type or dependency enters `agnara-core`.
- No provider can inspect the registry or reconstruct hidden exposures.
- Local mode declares no external origin; CDN mode has an exact version and
  SRI and remains opt-in.
- Online validation, credential persistence, query configuration and try-it
  are never enabled implicitly.
- Vendored assets must match their recorded byte count and SHA-256 digest.
- The upstream license and notice ship with the assets.
- OpenAPI 3.2 support is documented as basic and partial, not complete.

## Primary evidence

- https://github.com/swagger-api/swagger-ui/releases/tag/v5.32.14
- https://github.com/swagger-api/swagger-ui/pull/10721
- https://github.com/swagger-api/swagger-ui/issues/10897
- https://swagger.io/docs/open-source-tools/swagger-ui/usage/installation/
- https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/
- https://registry.npmjs.org/swagger-ui-dist/-/swagger-ui-dist-5.32.14.tgz
