# ADR 0045 — Protocol-Neutral Introspection Snapshot

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #188 (E8.1)

## Context

`agnara inspect`, its JSON form, `agnara graph`, an authorized discovery
endpoint and the Agnara Explorer shell must all answer from one model, or they
will disagree about what an application is. RFC 0003 and `ARCHITECTURE.md`
section 10 fixed the semantic shape and deliberately left the Python types
open; RFC 0003 lists them as its first open question.

Two constraints shape those types. Core may define neutral descriptor
contracts because several adapters and the CLI consume them, but core imports
no adapter, so exposure detail cannot come from inside core. And E8.2 must be
able to remove private capabilities, secrets, dependency instances and policy
internals before serialization — which is only meaningful if the model it
filters cannot reach a runtime object in the first place.

## Decision

`agnara.introspection` defines frozen slotted descriptors —
`IntrospectionSnapshot`, `AppDescriptor`, `CapabilityDescriptor`,
`InputDescriptor`, `DependencyDescriptor`, `ProviderDescriptor`,
`PolicyDescriptor`, `ExposureDescriptor` and `TypeReference` — plus
`describe_app` and `snapshot` to build them.

Every descriptor field is a string, a bool, a tuple of descriptors or a
`TypeReference`. Nothing holds a handler, a dependency instance, a provider
callable, a policy object or a compiled schema, so no traversal of a snapshot
reaches a runtime object. An architecture test reads the field annotations and
fails when a new field would break that, because the guarantee is worth more
than the convention.

JSON-shaped values — a compiled input's JSON Schema, an adapter's exposure
detail — are validated, copied and stored as canonical JSON text. A frozen
dataclass holding a mutable mapping would be lying about immutability, and a
read-only proxy would still be a view of something the caller can mutate.
Canonical text is immutable, comparable and deterministic to serialize.

The snapshot describes the *compiled* application: `describe_app` requires an
`ExecutionPlan` for every declared capability and refuses a plan that no
longer retains its definition. A capability published without its inputs,
dependencies and policies would be a worse answer than an error.

A policy is recorded by its type name alone. A policy's configuration
describes how authorization can be satisfied rather than that it applies, and
that is not the snapshot's job to publish.

Exposures are contributed by whoever owns the adapters, keyed by capability id,
as a transport name, an exposure name and namespaced JSON detail. Transport
availability is derived from them rather than declared separately, so the two
cannot disagree. An exposure naming an unknown capability is an error: silently
dropping it would understate what a capability is reachable through, which is
the fact a viewer consults the snapshot to learn.

The provider graph is described only when a `DIRegistry` is supplied. Each
node records what it provides, its scope, its provider kind and the bound
types it requires, so a relationship view (E8.5) is drawable from the snapshot
without walking the DI registry a second time.

`format` is `agnara-introspection` and `version` is `"0"`, versioned
independently of the Agnara release and of OpenAPI. `IntrospectionSnapshot`
exposes `json_data()`, its stable data form. Serializing is not publishing:
a snapshot reaching that method is already whatever the caller decided a
viewer may see, because filtering a serialized document leaves references,
counts and derived descriptions behind (RFC 0003 section 2).

Ordering is deterministic. Capabilities and inputs keep declaration order,
providers keep binding order, effects and scopes are sorted because their
sources are sets, and applications keep the caller's order because nothing
else carries meaning until a project descriptor exists.

`project` is optional. A project is not yet a runtime concept (EPIC 0A and
EPIC 1A), so a snapshot of one standalone application says so rather than
inventing a name.

## Alternatives

- Reuse `CapabilityDefinition` and `ExecutionPlan` as the discovery model:
  rejected because both hold the handler, the policies and the compiled
  schemas, so every consumer would be one attribute away from a runtime
  object and E8.2 would have nothing structural to rely on.
- Store JSON fragments as mappings: rejected because a frozen dataclass
  cannot hold one and remain immutable, and a proxy still aliases the source.
- Let core discover exposures itself: rejected because it would require core
  to import adapters, which ADR 0003 forbids.
- Build the snapshot from the registry alone, without plans: rejected because
  inputs, dependencies and policies exist only after compilation, and a
  snapshot silently missing them is worse than a refusal.
- Publish policy configuration: rejected because it describes how to satisfy
  authorization rather than that authorization applies.
- Emit JSON directly and filter the document: rejected by RFC 0003 — filtering
  after serialization leaks through references and counts.

## Evidence and limits

`tests/unit/test_introspection.py` covers declared metadata, signature-ordered
inputs with their compiled schemas, dependency and provider description
without callables or instances, adapter-contributed exposures and derived
transport availability, immutability, determinism, the JSON form, refusal of
uncompiled capabilities, mismatched plans, unknown exposure targets and
non-JSON or deeply nested detail, and that supplied detail is copied rather
than shared. `tests/architecture/test_introspection_contract.py` enforces the
frozen slotted shape, the field-type restriction and the declared version.

This is the complete internal model, not a publication decision. Visibility,
redaction and authorization (E8.2) must land before any snapshot is served
remotely. Also absent: CLI commands, a discovery endpoint, Explorer, project
and multi-app runtime semantics, and cross-surface consistency validation.
