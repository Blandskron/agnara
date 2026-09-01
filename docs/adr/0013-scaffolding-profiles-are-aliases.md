# ADR 0013 — CLI Profiles Are Scaffolding Aliases

- Status: Proposed

## Decision

Profiles such as `api`, `mcp`, `agentic`, `worker` and `full` select initial adapter scaffolding only.

They are not persisted as runtime application types.

## Example

```text
agnara app create tools --profile mcp
```

creates a normal `tools` app and adds MCP exposure scaffolding.

## Rationale

This preserves simple CLI ergonomics without contaminating the capability model with transport identity.
