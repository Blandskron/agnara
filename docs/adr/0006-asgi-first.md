# ADR 0006 — ASGI Compatibility Before Native Server Work

- Status: Proposed

## Decision

The first HTTP adapter targets ASGI interoperability.

Agnara will not build its own HTTP server in the initial roadmap.

## Rationale

ASGI provides immediate compatibility with existing Python servers and infrastructure. Native/Rust server work would distract from validating the capability architecture.

## Future

RSGI/native acceleration may be evaluated with benchmark evidence.
