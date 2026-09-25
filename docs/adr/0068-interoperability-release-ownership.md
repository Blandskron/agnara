# ADR 0068 — Interoperability evidence ownership

- Status: Accepted
- Date: 2026-09-11

## Context

Agnara's capability model is transport-neutral. HTTP, MCP and host
compositions must project the same compiled capability semantics without
moving protocol authority into core. A published interoperability claim needs
reproducible evidence for the scope it names.

## Decision

The release review owns interoperability evidence. Validate discovery,
invocation, errors, schema projection and authorization at each supported
surface through public adapter APIs. Keep protocol SDKs outside core.
Distinguish a supported contract from a version-pinned fixture and from
research in `docs/INTEROPERABILITY.md`.

A new protocol or framework integration needs its own reviewed contract and
conformance evidence before a support claim is made. Streaming, execution
identity and performance have separate gates; passing one does not close
another.

## Consequences

The exact current surface and limitations live in `docs/MATURITY.md` and
`docs/INTEROPERABILITY.md`. Release approval checks evidence for the selected
commit, rather than relying on an old milestone label.
