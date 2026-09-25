# Vision

## Today: a universal capability runtime

Agnara lets an application define a capability once and invoke or expose it
through independent adapters. Its Python 1.x kernel compiles declarations,
dependency graphs, policies, schemas and execution plans before invocation.
HTTP and MCP are supported projections; direct invocation, introspection, a
CLI and optional telemetry bridges are present. [Maturity](docs/MATURITY.md)
records the exact implementation and limits.

The central concept is **Capability**: what an application can do. An exposure
describes how a caller reaches it. A route, tool or future task must not become
the semantic source of truth.

## Tomorrow: a universal application platform

**Agnara — Universal Application Platform for the Agentic Era** is the long-term
product direction. Humans and coding agents should learn one coherent Agnara
model to build, inspect, modify and operate applications, whether they are
modular monoliths, services, APIs, agent systems or eventually distributed
systems. This is a research and design horizon, not a claim that those runtimes
ship today or a promise of a `2.0.0` release.

> Agnara owns the contract, not necessarily the implementation.

The kernel stays small, stable, capability-first, protocol-neutral and light
on dependencies. Independent platform packages may eventually define contracts
for data, durable tasks, events, workflows, identity, interfaces and
deployment. A database driver, broker, frontend renderer or model provider
could implement a contract without becoming a core dependency. Each contract
needs an accepted design and evidence before it becomes a supported API.

An application domain should not depend unnecessarily on deployment topology.
A capability may eventually move from local invocation to a process, service or
distributed deployment without rewriting its business meaning. Agnara does
not currently provide automatic remote invocation.

## North-star questions

1. Can a coding agent build, inspect, modify and operate this part of an
   application while reasoning primarily in Agnara concepts?
2. Does the design preserve a small, stable, protocol-neutral core?

A proposal must satisfy both. [Architecture](ARCHITECTURE.md) defines current
invariants; [roadmap](ROADMAP.md) defines the provisional future sequence.
