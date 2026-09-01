# ADR 0003 — Transport-Neutral Core

- Status: Proposed

## Decision

Protocol implementations live outside `agnara-core`.

## Dependency direction

Adapters depend on core. Core never imports adapters.

## Enforcement

CI architecture tests must enforce this rule.
