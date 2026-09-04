# ADR 0038 — Pinned Scalar Provider and Deferred Documentation Default

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #153

## Context

ADR 0018 named Scalar the leading modern-UX candidate but required it to pass
the same compatibility, asset, CSP, accessibility and size review as Swagger
UI and ReDoc before Agnara selected any default. E6.17 performs that spike
against `@scalar/api-reference@1.67.0`, published on 2026-08-28.

Scalar's evidence is promising but not complete. Its parser accepts OpenAPI
3.2, while the upstream 3.2 tracker still leaves API Reference, API Client,
mock-server and default-upgrade work open. The public OpenAPI documentation
still names Swagger 2.0, OpenAPI 3.0 and OpenAPI 3.1. Version 1.65.0 added 3.2
schema definitions as groundwork while noting that the workspace store still
used its 3.1 schemas. Agnara can exercise its 3.2 fixture without relabelling
it, but cannot claim complete end-to-end 3.2 conformance.

The npm package is broad: 40,679,445 unpacked bytes and 25 declared runtime
dependencies. The browser IIFE needed by Agnara is a self-contained
3,736,898-byte file, including the interactive API client; the separate ESM
chunks are not required. Adding the IIFE, exact-tag MIT license and manifest
increased the compressed `agnara-http` wheel from 841,266 to 1,937,150 bytes
in the local reproducible build.

The bundle also exposes security choices that generic embedding examples do
not settle. Telemetry defaults to enabled in its configuration schema, plugin
URLs can dynamically import arbitrary modules, agent/client features can
reach external services, authentication can persist locally, and its injected
CSS refers to `fonts.scalar.com`. An open accessibility report identifies
ARIA violations. Responsive media rules and ARIA markup exist, but source
presence is not WCAG or mobile-browser conformance.

Stoplight Elements 9.0.25 remains actively published, but brings 12 declared
dependencies including Scarf installation analytics and has no evidenced
complete 3.2 claim. RapiDoc 9.3.8 remains a small conceptual Web Component
integration, but its stale npm release and unfinished accessibility roadmap
make it weaker for a new default. Neither displaces Scalar as the modern-UX
candidate or Swagger UI as the compatibility baseline.

## Decision

`agnara-http` gains two internal providers for Scalar API Reference 1.67.0:

- `scalar` serves the exact verified standalone IIFE from the application
  origin;
- `scalar-cdn` uses the exact-version jsDelivr entrypoint with SHA-384
  Subresource Integrity and remains unavailable without explicit remote-asset
  permission.

The local file comes from `npm pack @scalar/api-reference@1.67.0
--ignore-scripts`; no package dependency is installed and no lifecycle script
runs. The npm tarball omits a license file, so the MIT license is copied from
the exact official release tag `release-2026-08-28-df40ed7`. The manifest
records both sources, tarball integrity, file size, SHA-256 and SRI. The exact
CDN entrypoint was byte-compared with the tarball file.

Every render uses a same-origin initializer rather than inline JavaScript. It
sets `telemetry: false`, `persistAuth: false`, `isEditable: false`, disables
agent and MCP affordances, supplies no proxy/authentication configuration,
sets `pluginUrls: []`, hides document download, and never shows developer
tools. The client and operation test buttons are hidden unless that specific
UI selected try-it. Explicit try-it changes presentation only; requests still
cross the normal HTTP authentication, policy and confirmation boundary.

Scalar injects its bundled CSS, so the provider declares inline-style CSP
support but not inline-script permission. Local mode declares no external
origin. Its unrequested `fonts.scalar.com` references are deliberately absent
from CSP, producing a system-font fallback instead of a hidden runtime network
dependency. E6.18 must confirm the resulting behavior, CSP, accessibility,
mobile layout, XSS payloads and try-it state in real browsers.

The provider declares OpenAPI 3.2.0 as the exact exercised input version and
names complete end-to-end 3.2 conformance, workspace-store 3.2 schema
selection and complete WCAG conformance as unsupported. Other versions are
refused by the provider contract rather than guessed or rewritten.

No documentation UI becomes Agnara's unconditional default. Swagger UI is
the current compatibility baseline, ReDoc is a useful read-only 3.1 reference
provider, and Scalar remains the leading modern-UX candidate. Default
selection stays deferred until E6.18 supplies comparable browser evidence and
the public composition API can express the selection without implicit
publication.

## Consequences

- Scalar can consume Agnara's canonical 3.2 document through the existing
  replaceable boundary without entering `agnara-core`.
- Local deployment has no documentation CDN, font, telemetry or plugin
  network dependency, at the cost of about 3.74 MB raw / 1.10 MB compressed
  wheel growth.
- CDN deployment is exact-version, SRI-protected and explicitly opt-in.
- Try-it remains independently selectable and credential persistence remains
  disabled.
- Accessibility and responsive source evidence is recorded honestly, while
  browser conformance remains a gate rather than an inferred claim.
- Stoplight Elements and RapiDoc remain possible application-supplied future
  providers; adding one requires no core change.

## Guardrails

- No Scalar type, package or UI semantic enters `agnara-core`.
- No npm install hook or declared dependency runs in Agnara installations.
- The local provider serves only bytes verified by size and SHA-256.
- The CDN provider uses an exact version and requires deployment permission.
- Telemetry, plugins, agent/MCP features, downloads, credential persistence
  and try-it are disabled unless the reviewed configuration explicitly needs
  the relevant surface.
- Remote fonts are blocked rather than silently added to local CSP.
- Partial OpenAPI 3.2 and accessibility evidence is never described as full
  conformance.
- No UI is selected as a default before E6.18 browser evidence.

## Primary evidence

- https://github.com/scalar/scalar/releases/tag/release-2026-08-28-df40ed7
- https://github.com/scalar/scalar/issues/6715
- https://github.com/scalar/scalar/issues/9725
- https://github.com/scalar/scalar/blob/main/documentation/openapi.md
- https://github.com/scalar/scalar/blob/main/documentation/configuration.md
- https://registry.npmjs.org/@scalar/api-reference/-/api-reference-1.67.0.tgz
- https://www.npmjs.com/package/@stoplight/elements
- https://www.npmjs.com/package/rapidoc
