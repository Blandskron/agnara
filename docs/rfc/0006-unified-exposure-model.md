# RFC 0006 — Unified Exposure Model

- Status: Answered by ADR 0070
- Date: 2026-09-06
- Tracking: GitHub Issue #271
- Initiative: I1
- Answered by: ADR 0070

## 1. Summary

Agnara should compile every protocol exposure through one neutral inventory
while leaving route, tool, skill and future event semantics in their adapters.

The proposal has two layers:

1. an adapter owns typed declaration, validation and its runtime artifact;
2. the same adapter compilation emits immutable neutral exposure records,
   which the project aggregates into one frozen registry.

The neutral record says *which compiled capability is reachable through which
named adapter surface*. It does not contain a route object, SDK model, request
binder, authorization callback or arbitrary configuration mapping.

Exposure declaration belongs to project composition. A bounded-context `App`
owns capability semantics and remains portable; the project chooses whether
and how those capabilities are reachable in its deployment.

This RFC proposes the semantic contract. Exact public class and method names
remain provisional until the implementation spike exercises both existing
adapters.

## 2. Current divergence

There are three answers today.

### HTTP

`agnara-http` has internal `_HTTPExposure` declarations containing method,
path, execution plan, bindings, body limit and OpenAPI publication metadata.
`_compile_exposures` validates them into a frozen route registry of
`_CompiledExposure`. The route table is the invocation truth, but HTTP exports
no supported composition API.

### MCP

`agnara-mcp` publicly exposes `Mcp(app)`, `mcp.tool(...)` and
`FrozenMcpTools`. Its registry freezes independently of `Agnara`, then later
functions pair those exposures with execution plans and SDK tools. The model
is typed and deterministic, but it is MCP-specific.

### Introspection

`describe_app(..., exposures=...)` receives a separate mapping keyed by
capability id. Its `ExposureDescriptor` is safe publication data, not the HTTP
route table or MCP tool registry. A caller can omit, duplicate or mistype what
the runtime actually exposes while every individual component remains valid.

The concrete drift is therefore:

```text
HTTP runtime routes ─┐
                    ├── maintained independently
MCP frozen tools ───┤
                    │
introspection map ──┘
```

A third adapter would need to invent a fourth lifecycle.

## 3. Goals

- one immutable project-wide answer to “where is this capability reachable?”;
- typed protocol-specific declaration and compilation;
- no protocol dependency or SDK object in `agnara-core`;
- one adapter compilation produces both dispatch truth and neutral inventory;
- deterministic identity, ordering, validation and diagnostics;
- multiple exposures per capability and multiple surfaces per protocol;
- introspection derived from compiled records, never handwritten in parallel;
- explicit separation of availability, discovery, publication and
  authorization;
- a staged path from the current HTTP and MCP implementations.

## 4. Non-goals

- a universal request, response, route, tool, message or stream abstraction;
- making a capability intrinsically HTTP, MCP, A2A or event-shaped;
- choosing server processes, network transports or deployment topology;
- flattening protocol-specific features into generic key/value configuration;
- implementing streaming, retries, task state or internal capability calls;
- selecting final public syntax in this RFC;
- adding a third adapter merely to prove the abstraction.

## 5. Invariants

1. Core never imports an adapter or protocol SDK.
2. A capability definition contains no exposure declaration.
3. A reusable `App` does not decide project deployment topology.
4. Every invocable adapter target has exactly one neutral compiled record.
5. A neutral record alone cannot dispatch an invocation.
6. Adapter-specific validation remains adapter-specific.
7. Exposure availability is not authorization.
8. Discovery and OpenAPI publication remain explicit filtering decisions.
9. No runtime surface starts until all selected exposure compilers succeed.
10. Frozen registries contain immutable values and deterministic order.

## 6. Ownership decision

Exposure declaration belongs to the **project composition root**, expressed
through typed adapter builders.

Conceptually:

```python
project = Agnara("shop")
project.include(payments)

public_http = HttpSurface("public")
agent_tools = McpSurface("agents")

public_http.get("/payments/{payment_id}", payments.get_payment)
agent_tools.tool(payments.get_payment)
```

These names are illustrative, not accepted API.

The capability says what the operation means. The app says which bounded
context owns it. The composition root says which deployment surfaces expose
it. This keeps the same app usable in an internal worker, a public service and
an agent-facing service without changing capability identity or importing an
adapter into application code.

An app package may provide helper functions that declare recommended adapter
bindings, but invoking those helpers is a project decision and their result is
still project-owned.

## 7. Identity model

One exposure is identified by three parts:

```text
adapter kind + surface name + adapter-local name
```

Examples:

```text
http + public + GET /payments/{payment_id}
mcp  + agents + payments.get_payment
```

- **adapter kind** is a stable, lowercase identifier such as `http` or `mcp`;
- **surface name** is a project-local stable identifier, allowing two HTTP or
  MCP surfaces with different audiences and configuration;
- **local name** is opaque to core and validated by the adapter. HTTP may use
  a method/path pair; MCP uses its tool-name grammar.

The tuple must be unique within a compiled project. A capability may have any
number of distinct exposures, including several on one surface. Two surfaces
may use the same local name because their full identities differ.

Core must not parse an HTTP path or apply MCP naming rules. It validates only
the adapter and surface identifiers, full-key uniqueness, capability
membership and deterministic ordering.

## 8. Proposed neutral types

Names remain provisional; the required shapes are:

```python
@frozen_slots_dataclass
class SurfaceId:
    adapter: str
    name: str


@frozen_slots_dataclass
class CompiledExposure:
    surface: SurfaceId
    name: str
    capability_id: CapabilityId
    discovery: ExposureDescriptor


class FrozenExposureRegistry(Mapping[ExposureId, CompiledExposure]): ...
```

`ExposureId` may be a dedicated frozen value or the structural key of
`CompiledExposure`; the implementation spike must choose one obvious lookup
API rather than expose both.

`discovery` is detached, canonical, explicitly publishable data. It may reuse
or evolve the existing `ExposureDescriptor`, but it cannot contain a runtime
artifact. Its adapter-specific detail is canonical JSON and defaults to no
detail. A route binder, SDK `Tool`, server object or callback is forbidden.

The neutral registry stores no typed adapter artifact. HTTP keeps its frozen
route registry; MCP keeps its compiled tool/invocation table. Composition holds
those results beside the neutral registry rather than placing opaque objects
inside core.

## 9. Adapter compiler contract

Each adapter compiler consumes frozen capabilities and their compiled
execution plans. It returns one result containing both:

- the adapter's typed immutable runtime surface;
- neutral records derived from exactly that surface.

Conceptually:

```python
@dataclass(frozen=True, slots=True)
class SurfaceCompilation[T]:
    runtime: T
    exposures: tuple[CompiledExposure, ...]
```

This generic envelope may live in composition tooling rather than core. What
matters is atomic derivation: callers do not construct a route table and then
separately describe what they remember constructing.

An adapter compiler must guarantee:

- every dispatchable local name appears once in `exposures`;
- every neutral record names the exact capability/plan retained by runtime;
- declaration order is deterministic;
- local collisions and invalid protocol syntax fail during compilation;
- the returned runtime surface is immutable for concurrent dispatch.

Core aggregates the emitted records and validates only cross-adapter rules.

## 10. Compilation lifecycle

The project lifecycle becomes:

```text
discover and mount apps
→ declare capabilities and typed adapter exposures
→ freeze capability/app registries
→ compile schemas, dependencies, policies and execution plans
→ compile every adapter surface
→ aggregate neutral exposure records
→ validate cross-surface identities and capability membership
→ freeze the exposure registry
→ build filtered discovery/publication projections
→ start runtime surfaces
```

Compilation is all-or-nothing from the runtime's perspective. A failed surface
may leave startup builder objects closed, but no partially compiled dispatcher
is published or started. Repeating successful compilation is idempotent.

Registration after the exposure freeze fails with a startup-compilation
diagnostic. The implementation must document lock ownership for mutable
builders and must not rely on the GIL.

## 11. Validation ownership

### Core/project aggregation

- adapter and surface identifiers are valid;
- full exposure identities are unique;
- each capability id exists in the frozen project registry;
- each record retains the project's exact compiled definition/plan identity;
- no surface compiler contributes records for another surface identity;
- source and aggregate order are deterministic.

### HTTP adapter

- method and path grammar;
- route ambiguity and collisions;
- input binding and body limits;
- HTTP response and OpenAPI publication metadata;
- surface/capability route collisions.

### MCP adapter

- MCP tool-name grammar and collisions;
- SDK tool schema projection;
- discovery/invocation name agreement;
- MCP task, resumption and interaction constraints.

Future adapters own equivalent protocol rules. Core never learns them.

## 12. Availability, discovery, publication and authorization

These four facts must not collapse into one boolean.

- **Availability:** a compiled runtime surface can dispatch this exposure.
- **Discovery:** this viewer may learn the exposure exists.
- **Publication:** a protocol document such as OpenAPI includes selected safe
  metadata about it.
- **Authorization:** this principal may invoke the capability now.

The frozen exposure registry is availability truth. `filter_snapshot` still
applies viewer-specific discovery and redaction before serialization. HTTP
OpenAPI publication remains explicit per exposure. Runtime authorization still
evaluates policy and cannot be granted by presence in any registry or document.

Security-sensitive order:

```text
compiled availability
→ capability visibility for this principal
→ field/detail publication policy
→ serialization
```

Invocation independently performs authentication mapping and authorization.
Hiding an exposure never disables it; publishing one never authorizes it.

## 13. Introspection projection

`describe_app(..., exposures=<handwritten mapping>)` is transitional. The
target accepts the frozen neutral registry (or a read-only projection of it)
and derives each capability's `ExposureDescriptor` tuple.

Transport availability continues to derive from surviving exposures, as ADR
0045 and ADR 0046 require. Surface identity must be preserved either as an
explicit descriptor field in the next introspection version or as canonical
adapter-namespaced detail during version 0. It must not be silently discarded.

An adapter may contribute less discovery detail than it uses at runtime. It
may not contribute a neutral availability record without a runtime target, or
a runtime target without a neutral record.

## 14. Protocol-specific features

The neutral registry is deliberately insufficient to implement dispatch.

HTTP retains methods, route matching, parameter binding, media types, response
serialization, problem details, documentation publication and static surface
routes. MCP retains tools, SDK schemas, interaction results, task capability
advertisement and protocol errors. Future event adapters retain delivery,
acknowledgement and broker semantics.

If a feature cannot be expressed by adapter kind, surface identity, local
name, capability identity and safe discovery detail, it stays on the typed
adapter artifact. The answer is not a generic `options: dict[str, Any]`.

## 15. Migration plan

### Phase 1 — neutral internal contract

- add frozen neutral identity/record/registry types in core;
- add aggregation validation and tests;
- do not export final composition syntax yet.

### Phase 2 — existing adapter bridges

- make HTTP compilation return its frozen route table and derived neutral
  records together;
- make MCP compilation return its tool/invocation surface and the same neutral
  record shape;
- retain current MCP entry points as provisional compatibility shims;
- derive introspection inputs from the neutral registry.

### Phase 3 — project composition API

- dogfood both adapters through one project compiler;
- settle typed public `Http` and MCP composition syntax;
- deprecate direct construction paths only after equivalent behavior and
  migration examples exist;
- keep protocol-specific builder methods familiar (`get`, `tool`, `skill`).

No phase changes capability ids. No adapter is published merely to complete
this migration.

## 16. Alternatives considered

### Put exposures on `CapabilityDefinition`

Rejected. A capability is protocol-neutral and an app must be portable between
projects with different deployment surfaces.

### Put all declarations on `App`

Rejected as the owner. It improves locality but makes a bounded context decide
deployment topology. App-provided helper functions remain possible.

### Store arbitrary adapter configuration in core

Rejected. A generic mapping would be a protocol type-erasure layer, weaken
validation and allow runtime objects to leak into supposedly frozen state.

### Let every adapter remain independent and merge only introspection

Rejected. That preserves multiple runtime truths and merely automates the
handwritten third answer.

### Make `ExposureDescriptor` the runtime model

Rejected. It is safe publication data and intentionally cannot dispatch.
Turning it into runtime configuration would couple discovery to execution.

### Use one global exposure name without surfaces

Rejected. A project may legitimately expose separate public/admin HTTP APIs or
separate MCP servers. Protocol kind plus local name cannot distinguish them.

### Let project aggregation validate protocol details

Rejected. It would make core understand paths, tool grammars and every future
adapter's semantics.

## 17. Questions the implementation spike answered

ADR 0070 records the decisions and the reasoning. In summary:

1. **Exact public names, and whether the compilation envelope is public.**
   `SurfaceId`, `ExposureId`, `CompiledExposure`, `SurfaceCompilation`,
   `FrozenExposureRegistry`, `compile_exposures` and `ExposureError`, exported
   from `agnara.exposure` and classified `provisional`. The envelope is
   public and generic over the runtime artifact, because it is the adapter
   compiler contract: without a named type for it, each adapter invents its
   own handoff shape and the fourth lifecycle this RFC exists to prevent
   reappears as a helper.

2. **Whether `ExposureId` is a dedicated value or a structural mapping key.**
   A dedicated frozen value. A duplicate must be named in a diagnostic before
   its record exists, and a lookup should not require constructing the record
   being looked up.

3. **How surface identity enters introspection version 0.** As
   adapter-namespaced canonical detail under the kernel-owned key `surface`,
   with no `INTROSPECTION_VERSION` bump. `filter_snapshot` already redacts
   exposure detail, so deployment topology is withheld by default — which a
   descriptor field would not have been.

4. **Standalone project compiler or an extension of `Agnara.compile()`.**
   Standalone. `Agnara.compile()` returns a governed public type that every
   Historical Reference Application depends on, and `ARCHITECTURE.md`
   section 5 warns against growing `Agnara` into a god object.

5. **The compatibility window for provisional `Mcp`, `FrozenMcpTools` and
   direct `describe_app(..., exposures=...)`.** All three keep working
   through `0.1.0a4`. `Mcp` gains a keyword-only `surface` and a
   `compile_surface()` beside the existing `compile()`; `describe_app` accepts
   the frozen registry as the supported shape and the mapping as the legacy
   one. Phase 3 below retires the legacy paths, with migration examples,
   once the public composition API exists.

One decision changed this RFC's own proposal rather than merely selecting
from it. Section 8 sketched `CompiledExposure.discovery: ExposureDescriptor`;
the implementation carries canonical JSON detail instead and lets
`agnara.introspection` derive the descriptor. `ExposureDescriptor` lives in
the introspection package, so the sketched field would have made availability
depend on publication and closed an import cycle. ADR 0070 records the
reasoning; the separation this RFC states in section 12 is now structural and
enforced by an architecture test.

## 18. Acceptance evidence for implementation

The implementation is complete when tests prove:

- one capability exposed through HTTP and MCP yields two records from actual
  compiled dispatch surfaces;
- multiple named surfaces of the same adapter do not collide;
- unknown capabilities and duplicate full identities fail at startup;
- mutating declarations after compilation fails;
- introspection cannot omit or invent a compiled exposure;
- filtering one viewer does not change runtime availability for another;
- HTTP and MCP dispatch retain their current protocol-specific behavior;
- core imports no adapter or SDK;
- frozen registries are deterministic and safe for concurrent reads.

Every item is covered by `tests/unit/test_exposure_model.py`,
`tests/integration/test_exposure_aggregation.py` and
`tests/architecture/test_exposure_boundaries.py`. The remaining work is phase
3: the public composition API, which is a separate task.
