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
→ resolve invocation dependencies
→ validate/coerce input
→ enforce policy
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

Protocol packages register exposures against the application through extension interfaces.

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

## 10. Discovery

Agnara should eventually expose a protocol-neutral capability manifest.

Illustrative shape:

```json
{
  "capabilities": [
    {
      "name": "send_payment",
      "effects": ["financial-write"],
      "risk": "high",
      "confirmation": "required",
      "idempotent": false,
      "exposures": ["http", "mcp", "a2a"]
    }
  ]
}
```

This manifest is not a replacement for OpenAPI, MCP discovery or A2A Agent Cards. It is Agnara's own introspection representation and should remain optional unless standardized later.

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

Protocol adapters attach exposures to capabilities.

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
payments ──► public application contract of users
```

is allowed.

```text
payments ──► users.adapters.http
```

is forbidden.

Architecture tests should eventually detect common cross-app boundary violations.

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
