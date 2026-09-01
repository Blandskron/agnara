# ADR 0012 — Modular Hexagonal Is the Default Scaffold

- Status: Proposed

## Decision

Generated production-shaped apps use a modular hexagonal architecture by default.

Each app owns its own:

```text
domain/
application/
adapters/
```

rather than placing all project domains into global technical-layer folders.

## Rationale

This combines Django-like modularity with ports-and-adapters boundaries and enables protocol/infrastructure replacement.

## Escape hatch

A `minimal` scaffold remains available for examples and tiny modules.
