# ADR 0068 — Interoperability Ownership for 1.0

- Status: Accepted
- Date: 2026-09-11

## Context

The retained A8 publication is a baseline, not a release train. Agnara now
works toward one real public release: `1.0.0`. Interoperability must therefore
be delivered as a coherent release outcome rather than as an optional adapter
exercise or a sequence of preview milestones.

The release owns the evidence that the same compiled capability model can be
consumed through the supported transport adapters without moving transport
semantics into core.

## Decision

`1.0.0` owns interoperability as a release gate. Its scope is deliberately
bounded:

- prove capability discovery, invocation, errors and schema projection across
  the supported HTTP, MCP and A2A surfaces;
- preserve the protocol-neutral core boundary;
- test integrations through public adapter APIs, not private implementation
  details;
- record reproducible conformance evidence before release approval.

Streaming, execution identity and performance remain separate release gates.
Their work may share tests or implementation seams with interoperability, but
none may be declared complete merely because another gate passed.

## Consequences

The roadmap and backlog may prioritize interoperability work independently,
but a `1.0.0` release cannot be authorized until its conformance evidence is
available. New protocols or framework integrations remain out of scope unless
they are accepted through their own design process.

This keeps the release promise legible: Agnara supports the adapters it ships,
and each adapter is verified as a projection of the same capability model.
