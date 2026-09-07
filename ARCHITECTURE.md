# Architecture

## 1. Architectural style

Agnara uses a hexagonal / ports-and-adapters architecture around a capability execution kernel.

```text
┌───────────────────────────────────────────────────────────────┐
│                         Application                           │
└──────────────────────────────┬────────────────────────────────┘
                               │
                     Capability Registry
                               │
       ┌───────────────────────┼────────────────────────┐
       │                       │                        │
 Schema Port             Dependency Graph         Policy Engine
       │                       │                        │
       └───────────────────────┼────────────────────────┘
                               │
                    Execution Plan Compiler
                               │
                        Execution Runtime
                               │
        ┌───────────┬──────────┼─────────┬───────────┐
        │           │          │         │           │
       HTTP        MCP        A2A      Events       Tasks
        │           │          │         │           │
     adapter      adapter    adapter    adapter     adapter
```

## 2. Core domain objects

### CapabilityDefinition

Immutable description of a callable application capability.

Candidate fields:

```text
id
name
description
input contract
output contract
dependency declarations
policy declarations
effects
risk
idempotency
streaming mode
task mode
timeouts
metadata
```

### CapabilityRegistry

Owns registered capability definitions.

Requirements:

- deterministic registration;
- duplicate detection;
- immutable/frozen state after compilation;
- fast lookup;
- stable identifiers;
- introspection;
- no dependency on a transport.

### Invocation

Transport-neutral request to execute a capability.

Candidate model:

```text
capability_id
arguments
context
deadline
metadata
principal
delegation
```

The exact representation must be defined by RFC before implementation.

### ExecutionContext

Execution-scoped state.

Must distinguish:

- immutable metadata;
- task-local values;
- resource handles;
- authenticated principal;
- delegation information;
- cancellation/deadline information;
- transport identity.

Transport-specific raw objects must not leak into general domain handlers.

If an application requires access to transport-specific data, that must occur through an explicit optional adapter capability.

### DependencyProvider

A provider contributes a value to an execution plan.

Providers must declare scope:

```text
singleton
application
invocation
transient
```

Additional scopes require ADR approval.

### ExecutionPlan

Compiled, immutable hot-path representation of how to invoke one capability.

Example conceptual pipeline:

```text
authenticate
→ enforce policy
→ validate/coerce input
→ resolve invocation dependencies
→ invoke handler
→ validate output
→ emit telemetry
→ return canonical result
```

The exact order is security-sensitive and must have explicit tests.

### Policy

Policies are independently testable rules evaluated against the capability and context.

Policy examples:

- authenticated principal required;
- required scopes;
- delegated authority;
- human confirmation;
- tenant access;
- rate class;
- allowed side effects.

### SchemaAdapter

Port between Python types and runtime/schema operations.

The core defines interfaces. Integrations implement them.

Possible adapters:

- standard Python/dataclasses;
- msgspec;
- Pydantic.

No adapter may redefine capability semantics.

### CanonicalResult / Failure

The runtime needs protocol-neutral success/failure semantics.

Do not use HTTP status codes as core errors.

Transport adapters translate canonical outcomes into protocol-specific representations.

## 3. Package boundaries

### `agnara-core`

Allowed responsibilities:

- capability model;
- registry;
- context;
- dependency graph;
- policies;
- execution planning/runtime;
- extension contracts;
- base schema interfaces;
- canonical errors;
- lifecycle.

Forbidden dependencies:

- HTTP framework;
- ASGI framework;
- MCP SDK;
- A2A SDK;
- OpenTelemetry SDK;
- Pydantic;
- msgspec;
- LLM SDK.

The standard library should be preferred aggressively here.

### `agnara-http`

Responsibilities:

- ASGI application adapter;
- routing;
- request decoding;
- response encoding;
- HTTP lifecycle;
- headers/cookies/query/path semantics;
- RFC 9457 mapping;
- OpenAPI generation;
- streaming/SSE/WebSocket features as separately approved.

`agnara-http` may depend on an ASGI utility library only after an ADR demonstrates why direct ASGI is insufficient.

The adapter's public surface is the composition API in
`agnara_http.composition`: seven names that declare exposures, compile an
immutable ASGI 3 application and project OpenAPI (ADR 0071). Every other
module is underscore-prefixed. The documentation UI providers, the Explorer
and the authorized discovery endpoint are implemented but not reachable from
that surface, because no product path renders a provider into a served route;
`docs/MATURITY.md` records their real status and
`docs/HTTP_COMPOSITION.md` states the limitation.

OpenAPI and browser documentation follow this one-way projection:

```text
Capability
+ compiled HTTP Exposure
+ Schema Port output
+ explicitly publishable policy/discovery metadata
        ↓
OpenAPI 3.2
        ↓
replaceable documentation provider
```

Swagger UI, ReDoc, Scalar or any later documentation provider is optional and
replaceable. No provider is a semantic dependency of `agnara-http`, and none
may enter `agnara-core`.

### `agnara-mcp`

Responsibilities:

- MCP server projection;
- discovery;
- tools;
- resources/prompts where Agnara semantics justify them;
- MCP auth integration;
- task/MRTR mapping;
- MCP protocol-specific errors.

Prefer official protocol SDK use at the adapter boundary over reimplementing the protocol.

### `agnara-a2a`

Responsibilities:

- Agent Card / skill projection;
- A2A tasks;
- streaming;
- protocol bindings;
- A2A security/version mapping.

### `agnara-events`

Responsibilities:

- event capability abstractions;
- AsyncAPI projection;
- broker-specific plugins.

The base events package must not hardcode Kafka, NATS or RabbitMQ.

### `agnara-telemetry`

Responsibilities:

- OpenTelemetry bridge;
- Agnara semantic spans/events/metrics;
- correlation across transports;
- optional GenAI/MCP semantic convention mapping.

### `agnara-cli`

Responsibilities:

- project introspection;
- capability graph display;
- generated machine-readable context;
- development server command;
- schema generation;
- diagnostics.

### When a package has a public surface

A distribution's `__init__.py` re-exports names and declares `__all__` only
once its composition API is one we are prepared to keep. Until then the
package ships its implementation in underscore-prefixed modules and declares
`__all__ = []`, which says "no public API yet" rather than leaving a reader to
guess from an empty file.

The current split:

| Package | Surface | Why |
| --- | --- | --- |
| `agnara` | public | the released kernel |
| `agnara-mcp` | public | MCP's tool and authorization shapes follow the protocol, not our design |
| `agnara-telemetry` | public | two hook classes over an OpenTelemetry contract |
| `agnara-cli` | public | supports the `agnara` console script |
| `agnara-http` | none yet | the `Http(...)` composition API is still the golden-design sketch in `docs/API_DESIGN.md` section 4, not stable syntax |
| `agnara-a2a`, `agnara-events` | none yet | reserved namespaces holding a package boundary; adapters are Post-v0.1 |

A package with no public surface is not a package without tests. `agnara-http`
is exercised through its private modules precisely because the transport
behaviour is settled while the way an application composes it is not.

## 4. Allowed dependency graph

```text
agnara-core
   ▲
   ├── agnara-http
   ├── agnara-mcp
   ├── agnara-a2a
   ├── agnara-events
   ├── agnara-telemetry
   └── agnara-cli
```

Cross-adapter imports are forbidden by default.

If `agnara-http` needs MCP behavior, that behavior belongs in a composition package or application layer, not a direct dependency.

## 5. Application composition

The application object is a composition root.

It must not become a god object.

Recommended split:

```text
Application
  owns Registry
  owns Lifecycle
  owns ExtensionManager
  triggers Compile
```

### The unified exposure model

Protocol packages do **not** register exposures against the application
object, and adding a second registry to it is how it would become the god
object above. The direction is inverted: each adapter compiles its own surface
and the project aggregates the results.

```text
Agnara.compile()                    →  FrozenCapabilityRegistry
adapter compiles one named surface  →  SurfaceCompilation(surface, runtime, records)
compile_exposures(capabilities, …)  →  FrozenExposureRegistry
```

`agnara.exposure` owns the neutral half. An exposure is identified by adapter
kind, project-local surface name and adapter-local name — `http:public
POST /refunds`, `mcp:agents billing.refund` — and the kernel treats the local
name as opaque text. It validates identity, uniqueness, capability membership
and order; it parses no path and applies no tool grammar.

Two layers, and the split is the point:

| Layer | Owns | Where |
| --- | --- | --- |
| Adapter | typed declaration, protocol validation, the dispatch artifact | `agnara-http`, `agnara-mcp` |
| Kernel | neutral identity, aggregation, one frozen availability registry | `agnara.exposure` |

An adapter returns both in one value, so a route table cannot be obtained
without the records derived from it. Each adapter derives its records from its
own compiled artifact rather than from the declarations that produced it, so
neither can describe something the other does not hold.

There is no open exposure registry. Aggregation takes the complete set of
surface compilations and returns the frozen result, so late registration is
structurally impossible rather than guarded by a flag.

The registry is availability truth and nothing more. Availability, discovery,
publication and authorization stay four separate facts: presence permits no
invocation, and hiding an exposure from one viewer disables it for nobody. See
ADR 0070 and RFC 0006.

A third adapter joins by returning the same envelope. The kernel needs no
change, which is the architectural test the model has to pass — not a reason
to build one.

## 6. Startup compilation

Startup compilation should transform author-friendly declarations into runtime-friendly immutable plans.

Potential phases:

```text
DISCOVER
→ NORMALIZE
→ VALIDATE GRAPH
→ COMPILE SCHEMAS
→ COMPILE DEPENDENCIES
→ COMPILE POLICIES
→ COMPILE EXPOSURES
→ FREEZE
→ START
```

Compilation failures should be explicit and fail fast.

## 7. Runtime phases

A runtime invocation must avoid repeated introspection.

Target:

```text
transport decode
→ locate compiled exposure
→ create invocation context
→ execute compiled plan
→ map canonical result
→ transport encode
```

## 8. Concurrency model

Requirements:

- Python 3.14;
- async-first but not async-only domain semantics;
- explicit support strategy for sync functions;
- `TaskGroup` for owned concurrent work;
- cancellation propagation;
- deadlines;
- context isolation;
- free-threading-safe registries after freeze.

Mutable global caches require locks or immutable replacement strategies.

## 9. Extension model

Extensions need lifecycle hooks but must not obtain unrestricted mutation access to internals.

Candidate hooks:

```text
on_register
before_compile
after_compile
on_startup
on_shutdown
before_invoke
after_invoke
on_error
```

Hot-path hooks must be compiled to avoid dynamic registry scans.

## 10. Discovery and documentation

Agnara exposes two distinct projections from one compiled application model.

### Protocol contracts

Each adapter projects only its exposures into the relevant protocol contract:

```text
HTTP exposures   → OpenAPI 3.2
MCP exposures    → MCP discovery
A2A exposures    → Agent Card / skills
Event exposures  → AsyncAPI
```

No protocol contract is the canonical representation of a capability.

For HTTP, `agnara-http` derives OpenAPI from the capability definition,
compiled HTTP exposure, schema port and policy/discovery metadata explicitly
approved for publication. Developers do not maintain a parallel OpenAPI file
for generated exposures.

Human OpenAPI interfaces sit behind an optional provider boundary:

```text
OpenAPI 3.2
   ├── Swagger UI provider
   ├── ReDoc provider
   ├── other evaluated provider
   └── no UI
```

The preferred production asset mode is version-pinned and self-hosted. CDN
loading is explicit opt-in with documented integrity and CSP consequences.

### Protocol-neutral introspection

Agnara also defines a read-only, versioned introspection snapshot for concepts
that OpenAPI cannot represent completely:

```text
Project
Apps
Capabilities
Exposures
Dependencies
Policies
Effects
Risk
Idempotency
Confirmation
Schemas
Transport availability
```

Core may define neutral descriptor contracts because multiple adapters and the
CLI consume them. Adapter-specific exposure details are contributed through
extension contracts; core does not import adapters.

The snapshot is a safe projection, not a dump of runtime objects. Publication
policy removes private capabilities, sensitive dependency/policy details,
secrets and unsafe examples before serialization.

Conceptual machine-readable shape:

```json
{
  "format": "agnara-introspection",
  "version": "0",
  "apps": [
    {
      "id": "payments",
      "capabilities": [
        {
          "id": "payments.refund",
          "effects": ["financial-write"],
          "risk": "high",
          "confirmation": "policy",
          "idempotency": "no",
          "exposures": ["http", "mcp", "a2a"]
        }
      ]
    }
  ]
}
```

`agnara.introspection` implements this contract: frozen slotted descriptors
whose fields are names, declared metadata and canonical JSON text, built from
a compiled application by `describe_app` and assembled by `snapshot`. The
format is `agnara-introspection` and the version is `"0"`, which states that
the contract is not yet stable. See ADR 0045.

Exposures are derived from the frozen exposure registry rather than described
a second time: `describe_app(..., exposures=<registry>)` reads the compiled
availability that section 5 aggregates, and transport availability follows
from it. Surface identity travels as canonical exposure detail during version
0, which means `filter_snapshot` redacts deployment topology together with
the rest of the detail. A handwritten mapping of capability id to descriptors
is still accepted and is the legacy shape; it asserts what a caller remembers
composing, which is exactly the drift ADR 0070 removed.

The concept list above is executable. `tests/architecture` reads it out of
this document and checks the model against it, and asserts that no descriptor
field can be published without a named decision, so removing a concept from
either side breaks a test rather than a promise.

Building a snapshot is not publishing one. `filter_snapshot` applies a
`DiscoveryVisibility` — a visibility rule deciding which capabilities a
principal may discover, plus an explicit set of published fields — and returns
a snapshot marked `filtered`. A surface that serves a snapshot to anyone
should refuse an unfiltered one. Hiding is discovery-only and never authorizes
or deauthorizes invocation. See ADR 0046.

### Agnara Explorer

Agnara Explorer visualizes the filtered protocol-neutral snapshot. It may be
served through HTTP initially, but HTTP and OpenAPI are not its data model.

The implemented shell is server-rendered HTML with no JavaScript, no
stylesheet and no external asset, over the same snapshot, visibility decision
and principal resolver the discovery endpoint uses. Read-only is therefore
structural rather than configured, and the content security policy can be
`default-src 'none'` with no exceptions. A hidden capability and an absent one
are the same `404`. See ADR 0052.
The CLI, agent tooling and Explorer should consume the same introspection
contract where possible.

Human UI and machine-readable discovery are separate surfaces. Deployments
must be able to disable all HTML interfaces while retaining an authorized
OpenAPI or introspection endpoint, or disable publication entirely.

Every surface that describes an application — the CLI's text, JSON, graph and
context renderings, the HTTP discovery endpoint, and MCP `tools/list` — must
agree for one viewer. `tests/integration` asserts that agreement, including
for MCP, whose scope filter predates the introspection layer and runs on its
own code path.

`agnara-http` serves the introspection snapshot through a discovery endpoint
that is authorized by construction: it takes a principal resolver, answers
`401` to an unidentified viewer unless anonymous discovery is opted into
explicitly, filters per request before serialization, and refuses a
shared-cacheable directive because the document is viewer-specific. It serves
the same document `agnara inspect --json` produces. See ADR 0049.

Visibility, schema publication, UI availability and interactive execution are
independent security decisions. Hiding an operation in a UI does not authorize
or deauthorize invocation.

See RFC 0003 and ADR 0018.

## 11. Native acceleration

Rust is not an architectural dependency.

Only introduce native code when benchmark evidence identifies a stable, high-value boundary such as:

- router lookup;
- schema encoding;
- plan dispatch;
- protocol parsing.

The Python reference behavior remains authoritative.

## 12. Architecture enforcement

CI should contain automated architecture tests ensuring:

- core does not import adapters;
- adapters do not import sibling adapters;
- no forbidden third-party packages enter core;
- public API imports remain intentional;
- cyclic package dependencies fail CI.

## 13. Project and app composition

Above the capability registry, Agnara introduces an explicit modular application layer:

```text
Project
   │
   ├── App: users
   │      └── Capabilities
   ├── App: payments
   │      └── Capabilities
   └── App: recommendations
          └── Capabilities
```

An app is a bounded context and registration boundary.

The app itself is transport-neutral.

Protocol adapters compile exposures for the capabilities a project selects, and the project aggregates them (section 5, ADR 0070).

Default generated app structure is documented in `docs/SCAFFOLDING.md`.

## 14. App dependency direction

Within an app:

```text
domain
  ▲
application
  ▲
adapters
```

Conceptually, dependencies point inward.

Framework-specific transport code lives at adapter edges.

Across apps:

```text
payments ──► users.application.contracts
```

is allowed.

```text
payments ──► users.adapters.http
payments ──► users.application.capabilities
payments ──► users.domain.models
```

is forbidden. Another app's `application/contracts.py` is the only public
cross-app Python import target. It contains transport-neutral types and
Protocols the app offers; `application/ports.py` instead describes services
the app requires and remains internal.

Importing a contract is not invoking a capability. Directly calling another
app's handler bypasses its compiled policy, dependency, deadline, telemetry
and failure boundaries. Internal capability invocation remains a separate
research decision under initiative I8.

Generated projects enforce these directions with a static architecture test
that resolves both absolute and relative imports without importing application
code. ADR 0066 records the complete rule and its alternatives.

## 15. CLI and scaffolding boundary

`agnara-cli` owns project/app generation.

Templates are not part of `agnara-core`.

The CLI may understand:

- project manifests;
- template versions;
- app architecture;
- installed exposures;
- safe file operations.

Core runtime behavior must never depend on whether code was generated by the CLI or written manually.

## 16. Project manifest

The initial design prototypes `agnara.toml` as a machine-readable composition/scaffolding manifest.

See `docs/PROJECT_MANIFEST.md`.

The manifest is not a secret store and must not replace typed runtime composition for advanced cases.
