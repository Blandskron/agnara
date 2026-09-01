# ADR 0002 — Capability Is the Core Primitive

- Status: Proposed

## Decision

The core application primitive is a protocol-neutral capability, not an HTTP route, MCP tool, A2A skill, event handler, or job.

## Consequence

Transports project capabilities into their own protocol models.

Business handlers should remain callable independently of those transports.
