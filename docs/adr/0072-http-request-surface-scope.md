# ADR 0072 — HTTP Request Surface Scope

- Status: Accepted
- Date: 2026-09-11
- Tracking: I7

## Context

The HTTP adapter must provide a clear, bounded request surface while preserving
the protocol-neutral capability core. The retained baseline supports cookies,
forms, multipart payloads and bounded file uploads; it must not accidentally
promise a full web framework.

## Decision

The HTTP adapter owns request parsing and HTTP-specific validation. Capability
handlers receive only the transport-neutral inputs selected by the adapter.
Bounded request bodies and uploaded `bytes` are supported within documented
limits.

Streaming request bodies, resumable uploads, session middleware, template
rendering and a general ASGI application framework are outside this decision.
Streaming is a separate `1.0.0` release gate and must be designed and tested as
a cross-cutting capability rather than added as an HTTP-only shortcut.

## Consequences

Applications needing a deferred concern may compose an outer ASGI layer around
the generated Agnara application. That composition must not cause core imports
of ASGI concepts or redefine capability semantics. Future expansion requires a
separate decision with security, cancellation and resource-limit evidence.
