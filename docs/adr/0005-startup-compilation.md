# ADR 0005 — Startup Compilation

- Status: Proposed

## Decision

Signature inspection, dependency graph analysis, metadata normalization, policy preparation and schema compilation should occur during startup/application compilation where practical.

## Goal

Keep runtime invocation close to an immutable execution plan rather than repeated reflection.

## Constraint

Startup diagnostics must remain understandable and deterministic.
