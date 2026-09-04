# ADR 0039 — Documentation Browser Conformance and a Deferred Default

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #155

## Context

ADRs 0036 through 0038 pinned Swagger UI, ReDoc and Scalar and recorded what
their source and package metadata appeared to require. Source inspection could
not prove that the pages actually render under the declared Content Security
Policy, keep untrusted OpenAPI markup inert, expose try-it only when selected,
avoid credential persistence, work at a mobile viewport or preserve a usable
keyboard entry point.

The ordinary test suite also needs to remain fast and runnable without a
browser download. Browser evidence therefore needs an explicit, required CI
lane rather than an implicit dependency on whatever browser happens to exist
on a developer machine.

## Decision

Playwright 1.62.0 is pinned as a workspace development dependency. It is not a
dependency of any distributable Agnara package. A required Linux CI job
installs the Chromium revision owned by that exact Playwright release and runs
the tests behind the explicit `AGNARA_RUN_BROWSER_TESTS=1` gate. Ordinary
pytest runs collect and skip them, so a missing browser never becomes a
platform-dependent failure or a false passing browser claim.

The documentation contract now serializes provider declarations into one
restrictive header set. It defaults every resource class to none, keeps
connections same-origin, adds declared external origins only to script and
style assets, and grants inline styles, inline scripts or a blob worker only
when requested. It also emits `no-store`, `nosniff`, `no-referrer` and denial
of framing. The test host sends these exact headers through Agnara's compiled
ASGI surface dispatcher.

The shared fixture drives the pinned local providers in Chromium
151.0.7922.34, revision 1234 from Playwright 1.62.0:

- Swagger UI 5.32.14 and Scalar 1.67.0 render the OpenAPI 3.2.0 fixture;
- ReDoc 2.5.3 renders the equivalent 3.1.0 fixture and the provider contract
  refuses 3.2.0 before a browser can receive a relabelled document;
- untrusted title and spec markup cannot execute, and its attempted remote
  image is blocked by CSP;
- Scalar's font origin and ReDoc's branding origin are observed as CSP-blocked
  and produce no successful external response;
- ReDoc's same-origin `blob:` search worker runs only with its declared worker
  privilege;
- Swagger and Scalar expose request controls only when that UI selected
  try-it, while ReDoc continues to refuse a nonexistent console;
- browser storage contains no authentication-, token-, bearer- or
  credential-named state after initial render;
- Swagger's computed OAuth redirect remains same-origin, no client secret is
  embedded and the unconfigured redirect route is absent rather than silently
  published;
- all three render without horizontal document overflow at 390 by 844 pixels,
  expose their fixture title in the accessibility tree and accept keyboard
  focus.

These are security, responsive and accessibility smoke tests, not complete
OpenAPI or WCAG conformance. Automated smoke coverage cannot resolve Scalar's
known ARIA defects, ReDoc remains incompatible with the canonical 3.2
artifact, and the public HTTP composition API is still provisional.
Therefore no documentation provider becomes an unconditional default.
Scalar remains the modern-UX candidate and Swagger UI the compatibility
baseline until those remaining product and conformance boundaries are
resolved explicitly.

## Consequences

- Browser claims now fail in a required CI job instead of living only in
  prose or source-byte assertions.
- The ordinary cross-platform quality gate does not download browser binaries;
  the aggregate `CI` status nevertheless requires the browser job.
- Provider pages share one deterministic CSP/security-header serializer.
- The XSS fixture proves defense in depth at the browser boundary: a renderer
  may retain inert markup, but the emitted policy prevents its remote load and
  event-handler execution.
- OAuth support is not implied by Swagger's built-in dialog. Publishing a
  redirect endpoint and configuring a public client require a later explicit
  composition decision.
- Selecting no default remains an explicit evidence-based decision, not an
  omission.

## Guardrails

- Playwright and browser binaries remain development/CI infrastructure only.
- Browser tests exercise pinned local assets; mutable or unapproved CDN
  resources are never fetched.
- Any successful response outside the ephemeral same-origin host fails the
  test.
- Expected CSP blocks are asserted by origin; unrelated page, console or HTTP
  errors fail.
- Browser tests may not be removed from the aggregate CI gate while Agnara
  documents these providers as supported.
- Mobile and accessibility smoke evidence must never be called WCAG
  conformance.
- A default provider still requires a separate public composition decision and
  evidence addressing known compatibility/accessibility gaps.

## Primary evidence

- https://playwright.dev/python/docs/intro
- https://playwright.dev/python/docs/browsers
- https://pypi.org/project/playwright/1.62.0/
- `tests/http/test_documentation_browser.py`
- `.github/workflows/ci.yml`
