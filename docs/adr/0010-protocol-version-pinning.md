# ADR 0010 — Explicit Protocol Version Support

- Status: Proposed

## Decision

Every protocol adapter declares exact supported specification lines and maintains conformance tests.

## Rationale

MCP, A2A, OpenAPI and related standards evolve independently of Agnara.

"Supports MCP" is not a sufficient compatibility claim.

## Documentation

Release notes must state supported protocol versions and known unsupported optional features.
