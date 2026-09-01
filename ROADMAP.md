# Roadmap

## Phase 0 — Constitution and experiments

Goal: make bad architectural shortcuts expensive before production code exists.

Deliverables:

- vision;
- principles;
- RFC 0001;
- golden API examples;
- dependency rules;
- benchmark harness design;
- proof-of-concept experiments for schema and ASGI choices.

Exit gate: maintainers agree on the capability model and package boundaries.

## Phase 1 — Core capability kernel

Deliver:

- registry;
- capability definitions;
- direct invocation;
- execution context;
- immutable metadata.

No HTTP yet unless required for a throwaway experiment.

## Phase 2 — Schema and dependency engine

Deliver:

- schema ports;
- standard Python adapter;
- DI graph;
- scopes;
- startup graph validation;
- lifecycle cleanup.

Exit gate: capability can execute with typed inputs and dependencies without transport involvement.

## Phase 3 — Compiled execution plans

Deliver:

- plan compiler;
- policy stage;
- deadlines;
- cancellation;
- canonical failures;
- telemetry hooks.

Exit gate: reflection is absent from common hot-path execution where avoidable.

## Phase 4 — HTTP

Deliver:

- ASGI adapter;
- routing;
- request binding;
- serialization;
- RFC 9457 mapping;
- OpenAPI 3.2 target;
- HTTP test client strategy.

Exit gate: a production-shaped CRUD example works without coupling domain functions to HTTP types.

## Phase 5 — MCP

Deliver:

- MCP tool projection;
- discovery;
- schemas;
- authorization bridge;
- interaction/task mapping research;
- conformance suite.

Exit gate: the exact same capability can be invoked by direct Python, HTTP and MCP.

## v0.1 — Architectural proof

The first public alpha should demonstrate the thesis, not feature completeness.

## Phase 6 — Agent-oriented policy and observability

Deliver:

- richer delegation model;
- structured side effects;
- confirmation;
- OpenTelemetry adapter;
- machine-readable introspection.

## Phase 7 — A2A

Deliver:

- Agent Card projection;
- skills;
- tasks;
- streaming;
- version negotiation.

## Phase 8 — Events and AsyncAPI

Deliver:

- event capability model;
- producer/consumer exposures;
- AsyncAPI projection;
- broker adapters outside core.

## Phase 9 — Distributed task adapters

Deliver task abstraction backed by external systems rather than embedding a broker in core.

## Phase 10 — Native acceleration

Only after measured bottlenecks.

Candidate experiments:

- Rust router;
- compiled serializers;
- dispatch table;
- protocol parsing.

Every native component must retain Python fallback/reference behavior where practical.

## Long-term

Agnara should become:

```text
small stable core
+
rapidly evolving adapters
+
protocol conformance suites
+
agent-readable capability graph
+
reproducible performance engineering
```

## Phase 0.5 — Modular project developer experience

Before HTTP becomes the center of examples, establish the project/app model and scaffolding contract.

Deliver:

- `agnara project create`;
- `agnara app create`;
- modular-hexagonal default template;
- profiles and `--with` exposures;
- explicit project manifest prototype;
- dry-run and non-destructive generation;
- machine-readable CLI output.

Exit gate:

A developer can create one project containing at least three apps with different exposure combinations while domain/application code remains transport-neutral.
