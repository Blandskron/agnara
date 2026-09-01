# ADR 0009 — Capability Execution Is the Observability Boundary

- Status: Proposed

## Decision

Agnara traces capability execution independently of transport.

Transport spans may wrap or link to the common capability span.

## Rationale

The same operation should be observable consistently whether invoked by HTTP, MCP, A2A, task, event or direct Python.
