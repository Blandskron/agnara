# ADR 0033 — The Documentation-Provider Contract

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #141

## Context

ADR 0018 and RFC 0003 decided the policy for browser documentation:
providers are optional and replaceable, pinned local assets are the secure
baseline, hiding is never authorization, and no provider may silently
downgrade the canonical OpenAPI 3.2 document.

None of that was expressed in code. There was no contract to implement, so
E6.13 through E6.19 had nothing to build against and every policy was an
honour system. A policy nobody can violate by accident is worth more than a
policy written down.

The risks are concrete. A provider handed the compiled registry can render an
exposure the projection deliberately withheld. A 3.1 renderer given a 3.2
document produces documentation that is confidently wrong. A provider that
needs a CDN by default turns a production deployment into a network
dependency nobody chose.

## Decision

The contract is four values and one protocol.

**What a provider is given** is exactly one already-filtered document source:
serialized bytes or its local URL, plus a title, an asset base URL, the
document's OpenAPI version, and whether try-it is enabled. Nothing else.
There is no route registry, no compiled
exposure, no execution plan and no capability, and a test asserts the field
set so a later field cannot smuggle one in. A provider renders what the
projection already decided to publish; it does not get to look further.

**What a provider returns** is one page, the assets it needs served locally,
and the Content-Security Policy it requires. Both are declared by the
provider rather than inferred by the adapter, because the adapter cannot know
what a renderer needs and guessing produces either a broken page or a policy
loose enough to be pointless.

**What a provider must declare** is its name, the exact OpenAPI versions it
was tested against, the features it does not support, and whether it needs
remote assets. `supported_openapi` and `unsupported_features` are required,
not optional: a compatibility claim made by silence is exactly the claim this
project refuses to accept. Declaring no unsupported features is allowed, but
it must be said.

**Asked for a version it does not support**, a provider becomes unavailable
with a diagnostic naming the version and the provider. It is never asked to
render, and the canonical document is never rewritten to suit it.

**The network is opt-in twice**: once by the provider declaring
`remote_assets`, and once by the deployment permitting it at render time. A
provider that returns an external origin without declaring it is a definition
error; one that declares it without deployment permission is unavailable.

Two same-origin rules exist because the obvious checks are wrong:

- a `//host/path` URL starts with a slash but is a protocol-relative network
  reference, so a same-origin path may not have a second leading slash;
- an asset path segment may not be `.` or `..`, so a provider cannot name a
  file outside the asset root it was given.

An empty registry is the supported no-UI deployment. OpenAPI generation never
requires a browser interface.

## Consequences

- E6.13 through E6.19 have something to build against.
- A provider cannot reach an unpublished exposure, because it is never handed
  anything that could reveal one.
- Incompatible documentation is absent rather than wrong.
- `agnara-http` acquires no UI dependency, asserted by an architecture test
  over both its imports and its declared dependencies.
- Providers must do more work up front: naming tested versions and
  unsupported features is a real obligation, and a provider that cannot
  honestly fill those in cannot register.
- The contract governs presentation only. It is not authorization, and must
  not be mistaken for one: filtering happens before a provider is reached.
- Packaging stays open. Whether providers ship as extras, separate
  distributions or application-supplied objects is still ADR 0018's question,
  and this contract is satisfied by all three.

## Guardrails

- No OpenAPI or UI type enters `agnara-core`.
- `agnara-http` imports and declares no browser documentation package.
- A provider receives only an already-filtered document.
- A provider receives exactly one document source, so a disabled schema route
  cannot leave a UI pointing at a URL that is not served.
- Try-it is off unless explicitly enabled, and no other setting turns it on.
- A version claim without named tested versions is refused at registration.
- An external origin requires both a provider declaration and deployment
  permission.
- Asset paths cannot traverse; documentation URLs cannot be
  protocol-relative.
