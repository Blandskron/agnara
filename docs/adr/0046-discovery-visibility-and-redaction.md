# ADR 0046 — Discovery Visibility and Redaction

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #190 (E8.2)

## Context

ADR 0045 made the introspection snapshot the complete internal model on
purpose: it describes everything about a compiled application. Nothing may
serve it. RFC 0003 section 2 requires the filtering to happen before
serialization, because filtering a serialized document leaks through
references, indexes and derived descriptions, and section 8 requires that
private capabilities not be published automatically, that viewing never
authorize invoking, and that the runtime not guess an environment and silently
publish private surfaces.

RFC 0003 also names five decisions that must stay distinct and warns against
accumulating ambiguous booleans — while also insisting that no single flag may
grant several publication decisions at once. Those pull in opposite directions
unless the decisions are named individually rather than bundled.

## Decision

`agnara.introspection` gains `filter_snapshot(snapshot, visibility, principal)`,
returning the snapshot that principal may see. Filtering rebuilds descriptors
rather than editing them, so an unpublished field is absent from the result
instead of present with an emptied value.

Two orthogonal decisions, deliberately separate:

**Which capabilities a principal may discover** is a `VisibilityRule`:
`visible(capability, principal) -> bool`. A rule receives the *described*
capability, never its definition, so it cannot reach a handler and cannot make
anything executable or unexecutable. Built-in rules are `ScopeVisible` (the
principal holds every declared scope — the same rule the MCP adapter already
applies to `tools/list`, so the two surfaces cannot disagree for one
principal), `AllCapabilitiesVisible` and `NoCapabilityVisible` (both named as
postures rather than defaults), and `Hiding(ids, rule)`, which composes.

**Which fields are published** is `DiscoveryVisibility(rule, published)`, where
`published` is a set of `DiscoveryField` members: description, effects, scopes,
safety (risk, confirmation, idempotency), inputs, dependencies, providers,
policies, exposures, exposure detail and type modules. Each is its own
decision; none implies another. This answers the ambiguity warning by naming
the decisions instead of collecting booleans whose interaction nobody can
state, and an architecture test asserts that publishing one field publishes
exactly that field.

`published` has no default. `identity_only`, `agent_safe` and `unrestricted`
are named starting points a composer chooses explicitly.

Three consequences are deliberate:

An application whose capabilities are all hidden is dropped, and the project
name goes with it, because an application name is itself a disclosure.

Transport availability is derived from the exposures that survive. Hiding
exposures therefore also hides transport availability: in this model transport
availability *is* the exposure list. Fabricating a coarse transport entry to
publish availability without route names would be inventing data the snapshot
never held; an adapter that wants coarse availability contributes a coarse
exposure name instead, which is its own publication choice.

`IntrospectionSnapshot` gains `filtered`, set only by the filter. A consumer
that serves a snapshot to anyone should refuse an unfiltered one. It is a
label for that check, not a claim that the publication decision was a good one.

Hiding remains discovery-only. A hidden capability stays registered and stays
invocable by anyone the policy layer allows (ADR 0008). The filter takes the
hiding decision from its caller rather than inventing private/internal
metadata on `CapabilityDefinition`, which is EPIC 1 territory and would let a
single authoring flag quietly govern more than one of RFC 0003's decisions.

## Alternatives

- Serialize and then filter the document: rejected by RFC 0003 — references,
  indexes and derived descriptions leak what was removed.
- One `public: bool` on the capability declaration: rejected because it would
  be exactly the single flag RFC 0003 forbids, silently coupling discovery,
  OpenAPI publication and UI presence.
- A safe default `published` set: rejected because any default is the runtime
  guessing an environment. Requiring the argument makes the decision visible
  in the composition code and in review.
- Blanking withheld fields in place instead of rebuilding: rejected because a
  descriptor built from a partially-blanked source is one refactor away from
  carrying a field nobody filtered.
- Publishing transport availability when exposures are withheld: rejected
  because it would require the snapshot to carry transports independently of
  exposures, reintroducing exactly the disagreement ADR 0045 removed.
- Redacting a policy's configuration rather than the policy: rejected because
  ADR 0045 already publishes only the type name; there is no configuration in
  the model to redact.

## Evidence and limits

`tests/unit/test_discovery_visibility.py` covers each rule, composition,
each named posture, every field as an independent decision, module redaction,
partial visibility, the empty result, source immutability, principal isolation
across sequential viewers, and refusal of invalid rules, fields and arguments.
`tests/architecture/test_introspection_contract.py` asserts that the
visibility module imports no definition, registry or plan, and that a filtered
snapshot is marked.

Limits: this is the decision, not a surface. Authentication, cache-control and
`Vary` semantics, the discovery endpoint (E8.6), the CLI (E8.3, E8.4) and
Explorer (E8.8 onward) still have to apply it. `ScopeVisible` treats a
capability that declares no scopes as visible to everyone, including an
anonymous viewer; that is honest about the declaration and is why `Hiding`
exists. Nothing here rate-limits, audits or logs discovery.
