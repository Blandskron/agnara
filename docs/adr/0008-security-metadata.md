# ADR 0008 — Security and Effect Metadata

- Status: Proposed

## Decision

Capabilities may carry structured metadata for scopes, effects, risk, confirmation and idempotency.

## Constraint

Metadata is never treated as authorization by itself.

Policy engines consume metadata and context to make enforceable decisions.

ADR 0077 fixes the cross-surface implementation: declared scopes compile into
the common execution plan as its first policy. Risk and effects remain
descriptive metadata; neither grants nor denies authority independently.
