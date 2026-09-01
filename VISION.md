# Vision

## Mission

Build a Python framework that is native to the software world of 2026 and beyond: typed, capability-centric, agent-aware, protocol-neutral, observable, secure, modular, and fast by architecture.

## Product statement

Agnara is a **universal capability runtime for Python**.

Developers define application capabilities once. Agnara compiles those declarations into executable plans and projects them into one or more transports such as HTTP, MCP, A2A, event systems, task systems, CLI, or internal invocation.

## The problem

The dominant web-framework abstraction is the route:

```text
method + path → handler
```

That abstraction is excellent for HTTP, but the modern application boundary is broader.

A single business operation may need to be:

- an HTTP endpoint for a frontend;
- an MCP tool for an AI assistant;
- an A2A skill for another agent;
- a task for asynchronous execution;
- an event consumer or producer;
- an internal strongly typed call;
- a CLI command;
- a human-approved operation.

Reimplementing the same operation for each protocol creates duplicated validation, policy, error semantics, telemetry, tests, documentation, and drift.

## Agnara's answer

The first-class abstraction is:

```text
Capability
```

A Capability describes what the application can do.

A Transport describes how a caller reaches that capability.

An Execution Plan describes how the capability is safely and efficiently invoked.

## What success looks like

Agnara succeeds when a developer can define an operation once and obtain:

- type-aware validation;
- dependency resolution;
- policy enforcement;
- consistent errors;
- observability;
- direct test invocation;
- HTTP exposure;
- OpenAPI documentation;
- MCP exposure;
- agent-readable metadata;

without the business function depending on any of those protocols.

## Long-term direction

Agnara should become a small and stable core surrounded by independent protocol and infrastructure adapters.

The core should age slowly.

Adapters should evolve rapidly.

That distinction is essential because MCP, A2A, OpenAPI, AsyncAPI, observability conventions, servers, schema libraries, and AI ecosystems will continue changing.

## What Agnara must never become

Agnara must not become a monolith that attempts to own every layer of an application.

Agnara should orchestrate contracts and execution, not absorb unrelated concerns.

## North-star test

Every major design decision should answer:

> Does this make a business capability more portable across protocols without coupling the domain to framework infrastructure?

If the answer is no, the feature probably belongs outside the core.

## Developer experience vision

Agnara should feel as productive for modular application construction as Django, while being architected for a different software era.

The intended workflow is:

```text
create project
→ add bounded-context apps
→ define capabilities
→ attach protocol exposures
→ compile one project graph
```

A developer should be able to grow from:

```bash
agnara app create health --architecture minimal
```

to:

```bash
agnara app create payments --with http,mcp,tasks
```

without changing the conceptual model.

Scaffolding is therefore part of the product architecture, not an afterthought.
