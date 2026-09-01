# ADR 0011 — Apps Are Bounded Contexts, Not Protocol Types

- Status: Proposed

## Decision

An Agnara app represents a cohesive bounded context/module such as `payments`, `catalog` or `users`.

HTTP, MCP, A2A, events and tasks are exposures attached to capabilities owned by that app.

## Consequence

`app-api` and `app-mcp` may exist only as CLI aliases.

They must not introduce API-specific or MCP-specific app base classes.
