# ADR 0014 — Explicit Project Manifest

- Status: Proposed

## Decision

Agnara will prototype a dedicated `agnara.toml` project manifest for app/scaffolding metadata.

## Goals

- deterministic CLI generation;
- human-readable app registry;
- agent-readable project map;
- no secret storage;
- version-controlled composition metadata.

## Constraint

The manifest must not prevent typed Python composition.

Before 1.0, evaluate whether this remains superior to storing equivalent metadata in `pyproject.toml`.
