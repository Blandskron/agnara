# ADR 0052 — The Read-Only Explorer Shell

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #204 (E8.8)

## Context

Every machine surface exists — CLI text and JSON, the relationship view, agent
context, the authorized discovery endpoint — and a human still has no way to
look at a compiled application.

RFC 0003 section 6 is explicit about what this must not become: not another
OpenAPI skin, its data source not the OpenAPI document, and it must show
transport availability including transports OpenAPI cannot describe. Section 8
requires that viewing never authorize invoking, and that interactive execution
be a decision separate from viewing. ADR 0040's asset policy applies: no
external asset in the production baseline.

## Decision

The Explorer is server-rendered HTML with **no JavaScript, no stylesheet and no
external asset**, served over the same filtered snapshot, the same visibility
decision and the same principal resolver the discovery endpoint uses.

Three properties follow from that, and each is the reason for it:

**Read-only is structural.** There is no client code to be made to write and no
interactive surface to secure. RFC 0003 asks for interactive execution to be a
separate decision; here it is absent, and the tests assert the absence of
forms, buttons, inputs and event-handler attributes rather than the absence of
a feature flag.

**The content security policy can be maximally strict.**
`default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors
'none'` is enforceable with no exceptions precisely because the page loads
nothing. Adding a stylesheet is a real decision with a real CSP consequence —
`style-src` has to open — and it should be made deliberately in E8.9 or E8.11
rather than inherited from this shell. The consequence is an unstyled page, and
that is the trade this MVP accepts.

**A human and a program cannot be identified differently.** Principal
resolution moved out of the discovery dispatcher into one shared function, so
both surfaces keep the three outcomes distinct: a principal, no recognised
identity, and a resolver that failed. Collapsing any two would be a security
bug, and now it would be one bug rather than two.

Deep links are real URLs on stable logical identifiers: `<base>` for the index
and `<base>/<capability id>` for one capability. The Explorer owns its whole
subtree and refuses at startup to shadow a capability route anywhere under it,
not merely at its root.

**A hidden capability and an absent one are the same `404`.** Distinguishing
them would publish the existence of something the visibility decision withheld.
The two problem documents differ only in the target the client itself asked
for.

Every value an application controls — descriptions, effect labels, exposure
names, the project name — is escaped, and a payload test drives every one of
them through both pages.

The human states RFC 0003 names are rendered: an empty result is a page saying
nothing is visible rather than an error; a partial view names the withheld
fields rather than showing them as their declared defaults; an unidentified
viewer is challenged. A loading state does not exist and cannot, because the
page is complete when it arrives — that is a consequence of the design, not an
omission from it.

## Alternatives

- A single-page application over the discovery endpoint: rejected. It would
  need `script-src`, ship an asset, and make "read-only" a property of code
  rather than of the surface. It would also make the Explorer's data path a
  second consumer of the endpoint rather than the same filter.
- Render OpenAPI: rejected by RFC 0003 in as many words. It cannot represent
  MCP or A2A availability, which is the fact this surface exists to show.
- Ship a stylesheet inline: deferred. It requires opening `style-src`, and the
  MVP's value is the strict policy. E8.9 and E8.11 should decide it with the
  views and the accessibility work that need it.
- Serve the Explorer without authorization: rejected. It is a viewer-specific
  document like the endpoint's, and the same rules apply.
- Distinguish hidden from absent: rejected. `403` on a hidden capability would
  confirm it exists.
- Its own principal resolution: rejected. Two resolutions are two chances to
  read a failed resolver as anonymous.

## Evidence and limits

`tests/http/test_explorer_shell.py` covers base-path validation, subtree
reservation, the shared authorization rules at compile time, the index and its
deep links, non-HTTP transport availability, provenance, the "seeing is not
authorization" statement on every page, the capability page's published facts,
withheld fields being named rather than defaulted, the empty result, a viewer
without a scope, hidden and absent producing the same answer, the challenge,
a failing resolver, the strict policy together with the absence of anything to
load, read-only by construction, XSS payloads in every application-controlled
field on both pages, `405` with `Allow`, `HEAD`, delegation outside the
subtree, and a nested path that is not a capability.

Limits: no styling, no schema/dependency/policy detail views beyond what the
shell lists (E8.9), no Explorer-specific authorization and cache-control suite
(E8.10), no accessibility, keyboard, screen-reader or responsive tests (E8.11),
no search, no try-it, and no write operation. No real-browser test yet: the
page has nothing a browser would execute, so the existing browser job's value
here is accessibility and rendering, which is E8.11's subject.
