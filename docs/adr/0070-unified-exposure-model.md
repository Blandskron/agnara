# ADR 0070 — Unified Exposure Model

- Status: Proposed
- Date: 2026-09-07
- Initiative: I1 Unified exposure model
- Tracking: GitHub Issue #293
- Answers: RFC 0006
- Related: ADR 0003, ADR 0005, ADR 0011, ADR 0045, ADR 0046, ADR 0065, ADR 0068

## Context

RFC 0006 recorded three independent answers to one question. `agnara-http`
compiled private `_HTTPExposure` declarations into a frozen route registry;
`agnara-mcp` froze an independent `FrozenMcpTools` table on its own lifecycle;
and `describe_app(..., exposures=...)` accepted a mapping written by hand.

The third one was not merely redundant, it was empty. Nothing in the shipped
code filled that mapping — only tests did — so every real application served
HTTP and MCP traffic while its introspection snapshot reported no exposures at
all. A caller could omit, duplicate or mistype what the runtime exposed and
every individual component stayed valid.

RFC 0006 proposed the semantic contract and left five questions to an
implementation spike. This ADR records what the spike decided, and the
implementation lands with it.

## Decision

### Declaration belongs to the composition root

Not to the capability, and not to the `App`. A capability says what an
operation means; an `App` says which bounded context owns it (ADR 0011,
ADR 0065); the project says which deployment surfaces expose it. An app
therefore runs unchanged in an internal worker, a public service and an
agent-facing service, and application code imports no adapter to stay
portable.

### An exposure is identified by adapter, surface and local name

```text
adapter kind + surface name + adapter-local name
```

`SurfaceId(adapter, name)` names one deployment of one protocol, so
`http:public` and `http:admin` coexist and may reuse local names.
`ExposureId(surface, name)` is the full identity, and the local name is opaque
to the kernel: HTTP uses `POST /refunds`, MCP uses `billing.refund`, and the
kernel validates neither grammar.

The kernel validates only what it owns — that adapter and surface identifiers
are lowercase ASCII words, that a local name is printable and bounded, that a
full identity is unique in a project, and that every record names a capability
the project actually compiled.

### `ExposureId` is a dedicated value, not a structural key

RFC 0006 left this open. A dedicated value wins for two concrete reasons the
spike ran into: a duplicate must be *named* in a diagnostic before its record
exists, and a lookup should not require constructing the thing being looked
up. `registry[ExposureId(surface, "POST /refunds")]` reads correctly;
building a whole `CompiledExposure` to find one does not.

### An adapter returns dispatch truth and neutral records together

```python
@frozen_slots_dataclass
class SurfaceCompilation[RuntimeT]:
    surface: SurfaceId
    runtime: RuntimeT
    exposures: tuple[CompiledExposure, ...]
```

The kernel is generic over `runtime` precisely so that it never names an
adapter type. It reads `surface` and `exposures` and nothing else. The reason
`runtime` travels with the records at all is atomic derivation: a caller
cannot obtain a route table without the records derived from it, so the two
cannot drift.

Each adapter derives its records **from its own compiled artifact**, not from
the declarations that produced it. `agnara_http._compile_exposure_surface`
iterates the frozen route registry; `Mcp.compile_surface` iterates the frozen
tool table. A record therefore cannot describe a target the runtime does not
hold, and a held target cannot go unrecorded.

### Availability is derived once and frozen once

`compile_exposures(capabilities, compilations)` validates the cross-adapter
rules and returns `FrozenExposureRegistry`. There is deliberately **no open
collecting registry**. Aggregation takes the complete set and returns the
frozen result, so no caller observes a half-populated view and no code path
can register an exposure after the freeze. The failure ADR 0005 guards against
is structurally absent here rather than prevented by a flag.

Introspection derives descriptors from that registry.
`describe_app(..., exposures=<registry>)` is the supported path; the mapping
form remains accepted, because it is governed public API rather than an
accidental internal, and RFC 0006 section 15 retires it once the composition
API lands.

### A compiled exposure carries canonical JSON, not a descriptor

RFC 0006 section 8 sketched `discovery: ExposureDescriptor` as a field. The
spike changed it: `CompiledExposure` holds `detail`, adapter-owned canonical
JSON text, and `published_detail()` derives the publication shape.

Two reasons, and the second is the load-bearing one.

`ExposureDescriptor` lives in `agnara.introspection`, and importing it from
`agnara.exposure` creates a real import cycle: `agnara.introspection.builder`
must import the exposure registry to derive from it, and importing
`agnara.introspection.descriptors` executes that package's `__init__`.
Avoiding the cycle by moving the type would put a publication concern in the
availability layer.

That constraint pointed at the better design. RFC 0006 section 12 already
separates availability from publication, and this makes the separation
structural: `agnara.exposure` depends on nothing in `agnara.introspection`,
enforced by `tests/architecture/test_exposure_boundaries.py`.

### Surface identity reaches introspection as detail, in version 0

RFC 0006 section 13 allowed either a new descriptor field or adapter-namespaced
detail, and forbade discarding it. Detail wins for version 0: no
`INTROSPECTION_VERSION` bump, no premature serialized field, and one
consequence worth stating on its own.

`filter_snapshot` already drops exposure detail for a viewer without
`DiscoveryField.EXPOSURE_DETAIL`. Carrying the surface name there means
deployment topology — that a project runs a separate `admin` HTTP surface — is
redacted by default and published only deliberately. That is the correct
default for a topology fact, and it would not have been the default for a
descriptor field.

The key `surface` is kernel-owned. An adapter that sets it is refused, so a
record cannot disagree with its own identity.

### Orchestration is a function, not a method on `Agnara`

RFC 0006 asked whether this lands as a standalone compiler or an extension of
`Agnara.compile()`. Standalone, for two reasons. `Agnara.compile()` returns
`FrozenCapabilityRegistry`, a governed public type that all nine Historical
Reference Applications depend on; changing its return type is a breaking change
that buys nothing. And `ARCHITECTURE.md` section 5 warns specifically against
`Agnara` becoming a god object, which is what accumulating every compilation
phase onto it would produce.

### A third adapter joins without kernel changes

`SurfaceId` accepts any lowercase adapter word, `SurfaceCompilation` is generic
over the runtime artifact, and the local name is opaque. An A2A or event
adapter contributes records the same way HTTP and MCP do. No third adapter was
built to prove this; RFC 0006 section 4 rules that out as a non-goal, and two
adapters through one model is the evidence.

## Threat analysis

**A record could smuggle a runtime object into the kernel or a snapshot.**
Detail passes through `agnara._json.canonical_json`, which refuses anything
that is not plain JSON, caps nesting at 64 levels and rejects non-finite
numbers. `CompiledExposure` holds an `ExposureId`, a `CapabilityId` and text;
an architecture test asserts nothing else is reachable.

**An exposure could advertise a capability the project does not have.**
`compile_exposures` checks membership against the frozen capability registry
and fails closed. Without it, a snapshot could describe a capability that does
not exist, which is both an information-disclosure surface and a way to make
clients call something absent.

**Two capabilities could silently share one wire name.** Last-write-wins would
route a request to the wrong capability. Duplicate full identities fail at
startup, in the adapter for its own surface and again in aggregation across
surfaces.

**Presence could be mistaken for permission.** The registry carries no policy,
principal or plan, and cannot invoke anything. Invocation still evaluates the
plan's policies. Hiding an exposure from a viewer does not disable it, and
publishing one does not authorize it; a test asserts availability is unchanged
by filtering.

**Deployment topology could leak.** Addressed above: surface identity travels
as detail and is redacted with it.

**A local name could corrupt a document or a diagnostic.** Control characters
are refused and length is bounded at 512 characters, so an adapter cannot push
an unbounded or newline-bearing name into a frozen registry, a log line or a
published document.

## Consequences

### Positive

- One answer to where a capability is reachable, derived from compiled
  dispatch surfaces rather than asserted beside them.
- Introspection can no longer omit or invent an exposure; the empty
  `exposures` field in every real snapshot is fixed at its cause.
- Two surfaces of one adapter become expressible, which they were not.
- The kernel gained no protocol dependency and no third-party import.
- Task 03 can build the public HTTP composition API on a settled model.

### Negative

- The word "surface" now means two things inside `agnara-http`: an RFC 0006
  adapter surface, and the static documentation response `_HTTPSurface` has
  meant since ADR 0034. Renaming either today would either contradict the RFC
  or churn a shipped internal. The public HTTP spelling is Task 03's to
  settle, and it should retire the collision.
- `Mcp` has two compile entry points. `compile()` returns the tool table the
  SDK projection consumes; `compile_surface()` returns it with records.
  Keeping both avoids a breaking change to a published adapter's public API
  during alpha, at the cost of one extra method until RFC 0006 phase 3.
- `describe_app` accepts two exposure shapes, and the weaker one is still
  legal.
- Aggregation is a separate call a composition root must remember. Nothing
  fails if it is skipped; the snapshot simply reports no exposures, exactly as
  it did before. Making it unskippable requires the composition API.

## Alternatives considered

**Put exposure declarations on `CapabilityDefinition`.** Rejected: a
capability is protocol-neutral and an app must be portable between projects
with different deployment surfaces.

**Put them on `App`.** Rejected as the owner. Better locality, but a bounded
context would decide deployment topology. An app package may still offer
helper functions that suggest bindings; invoking one stays a project decision.

**Store arbitrary adapter configuration in the kernel.** Rejected. A generic
`options: dict[str, Any]` is protocol type erasure: it weakens validation and
lets runtime objects leak into supposedly frozen state.

**Merge only introspection and leave the adapters independent.** Rejected.
That preserves two runtime truths and merely automates the handwritten third
answer instead of removing it.

**Make `ExposureDescriptor` the runtime model.** Rejected. It is safe
publication data and intentionally cannot dispatch; promoting it would couple
discovery to execution.

**One global exposure name with no surface.** Rejected. A project may
legitimately run separate public and admin HTTP APIs, or two MCP servers.
Adapter kind plus local name cannot distinguish them.

**Let aggregation validate protocol details.** Rejected. The kernel would
have to understand paths, tool grammars and every future adapter's semantics.

**Change `Agnara.compile()` to return a richer result.** Rejected above:
breaking, and it grows the god object ADR 0003 and ARCHITECTURE.md section 5
warn about.

## Migration

No capability id changes, no exposure semantics change, and no runtime
behaviour changes for an application that does not use the new model.

One deliberate break, in an internal path: `Mcp.__repr__` now includes the
surface name, because `Mcp('users', 0 tools, open)` could no longer identify
which of two servers it described. A repr is a diagnostic rather than a
contract, and alpha release documentation scopes the alpha public API as
changeable; the repository's own test was updated in the same change.

`Mcp(app)` keeps its signature; `surface` is keyword-only with a `"default"`
value. `Mcp.compile()`, `FrozenMcpTools`, `describe_app`, `_compile_exposures`
and every HTTP dispatch path are unchanged.

## Revisit when

RFC 0006 phase 3 — the public composition API in Task 03. That change settles
the public spelling of `Http(...)` and MCP composition, may retire the
`describe_app` mapping form and the second `Mcp` compile entry point, and
should remove the "surface" collision inside `agnara-http`. Promoting any of
these seven names to `stable` remains a separate decision gated by
`0.1.0b1` and `0.1.0rc1`.
