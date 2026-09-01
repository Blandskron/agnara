# Engineering Principles

These principles are architectural constraints, not marketing slogans.

## P1 — Capability-first

Domain operations are capabilities. Routes, tools, skills, topics, jobs, and commands are exposures.

No transport may become the canonical representation of a capability.

## P2 — Dependency inversion at every boundary

Core code may define interfaces needed by adapters.

Adapters may depend on core.

Core must not import protocol implementations.

Forbidden direction:

```text
agnara-core → FastAPI / Starlette / MCP SDK / A2A SDK
```

Allowed direction:

```text
agnara-http → agnara-core
agnara-mcp  → agnara-core
agnara-a2a  → agnara-core
```

## P3 — Minimal core

The core contains only semantics shared by multiple transports:

- capability definitions;
- registry;
- invocation;
- dependency graph;
- execution plans;
- context;
- policies;
- schema abstraction;
- errors;
- lifecycle primitives;
- extension contracts.

If a feature only makes sense for HTTP, it belongs in the HTTP package.

## P4 — Python types are the authoring surface

Developers should not maintain parallel schemas manually.

Type information is transformed through replaceable schema adapters.

The core must not require a specific model library.

## P5 — Compile once, execute cheaply

Reflection, dependency graph construction, signature analysis, schema compilation, and policy normalization should happen during application construction or startup whenever possible.

Hot-path invocation should use immutable/precompiled execution metadata.

## P6 — Concurrency is explicit

Python 3.14 free-threading means global shared mutable state is unsafe by default.

The runtime must document:

- mutable state ownership;
- synchronization strategy;
- task-local state;
- request/invocation scope;
- cancellation semantics;
- deadline semantics.

## P7 — Structured concurrency

Background work must have ownership.

Unbounded orphan tasks are forbidden in core runtime code.

Use structured concurrency concepts and explicit lifecycle scopes.

## P8 — Protocol semantics are not flattened

Transport-neutral does not mean pretending all protocols are identical.

Agnara defines a common semantic core while adapters preserve protocol-specific capabilities.

For example:

- HTTP status and headers belong to HTTP;
- MCP elicitation/MRTR belongs to MCP;
- A2A task lifecycle belongs to A2A.

Adapters map common concepts and expose protocol-specific extensions without contaminating core.

## P9 — Security metadata is executable

Policies are not documentation-only decorators.

Risk, scopes, side effects, approval requirements, delegation and idempotency metadata must be available to enforcement code and discovery surfaces.

## P10 — Agent-readable by design

Capability metadata must be machine-readable.

Descriptions alone are insufficient. Agents need structured information about:

- effects;
- permissions;
- failure modes;
- idempotency;
- confirmation;
- cost hints;
- latency hints;
- streaming;
- task behavior.

## P11 — Observability is not middleware glue

Tracing should surround capability execution itself so that all transports produce a common execution trace.

## P12 — Standards first

Prefer established standards:

- Python typing;
- JSON Schema;
- OpenAPI;
- RFC 9457 for HTTP problem details;
- MCP;
- A2A;
- AsyncAPI;
- OpenTelemetry.

Do not invent proprietary equivalents without an approved ADR.

## P13 — Provider neutrality

No specific LLM, model vendor, database, broker, cloud, schema library, auth provider, or HTTP server is part of the conceptual core.

## P14 — Evidence before claims

No performance, compatibility, conformance, security, or scalability claim may be published without a reproducible test.

## P15 — Backward compatibility is intentional

Before 1.0, breaking changes are allowed but documented.

After 1.0, core contracts require explicit deprecation and migration policy.

## P16 — Human-friendly and agent-friendly

Repository structure, APIs, errors, documentation, test names, architecture metadata and CLI output should be understandable by both developers and coding agents.

Agent friendliness must improve clarity, not create a second hidden architecture.

## P17 — Apps model domains, not transports

An app is a bounded context.

`payments`, `catalog`, and `users` are valid app identities.

`http`, `api`, `mcp`, and `controllers` are technical concerns and should not become the business module identity.

## P18 — Convention without hidden coupling

Agnara should generate useful conventions like Django, but every generated boundary must remain normal Python code that can be inspected, edited and tested.

## P19 — Scaffolding must be non-destructive

Generators must be deterministic, support dry runs, and refuse to overwrite user work by default.

## P20 — Complexity is incremental

A simple app should remain simple.

Architecture should allow growth into domain/application/adapters without forcing every project to begin with maximum ceremony.
