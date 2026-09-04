# ADR 0010 — Explicit Protocol Version Support

- Status: Proposed
- Updated: 2026-09-04
- Tracking: GitHub Issue #162

## Decision

Every protocol adapter declares exact supported specification lines and maintains conformance tests.

## Rationale

MCP, A2A, OpenAPI and related standards evolve independently of Agnara.

"Supports MCP" is not a sufficient compatibility claim.

## Documentation

Release notes must state supported protocol versions and known unsupported optional features.

## MCP baseline

The first `agnara-mcp` line targets the `2026-07-28` MCP specification through
the official Python SDK pinned exactly to `mcp==2.1.1`. The adapter publishes
one deterministic tuple, `SUPPORTED_MCP_PROTOCOL_VERSIONS`, containing only
`2026-07-28`.

The specification revision and SDK release are separate pins. The date-shaped
revision identifies wire semantics; the package version identifies the tested
implementation dependency. Upgrading either requires a reviewed change,
lockfile refresh, conformance evidence and release-note assessment.

The SDK is a dependency of `agnara-mcp`, never `agnara` core or another
adapter. MCP SDK types may implement the protocol boundary, but they do not
become capability, policy, schema or canonical-error semantics.

## Revision boundary

`2026-07-28` replaces the required session handshake with stateless,
self-contained requests. Each request identifies its protocol revision and
client capabilities in `_meta`; Streamable HTTP also provides
`MCP-Protocol-Version`, `Mcp-Method` and, where applicable, `Mcp-Name` headers.
The revision uses JSON Schema 2020-12 for tool schemas and makes extensions
such as Tasks explicitly opt-in.

Agnara does not advertise legacy revisions merely because SDK 2.1.1 can
negotiate them. Supporting a revision means Agnara has compatibility and
conformance tests for its own projections and failure mappings. E7.8 owns that
evidence. Until then, E7.1 records a target baseline rather than claiming a
complete server implementation.

## Deferred surface

This decision does not implement or claim:

- tool projection, schema mapping or discovery (E7.2–E7.4);
- authorization or canonical interaction-required mapping (E7.5–E7.6);
- Tasks, MRTR or other extension behavior (E7.7);
- official SDK conformance (E7.8);
- legacy protocol negotiation by Agnara.

## Evidence

- https://modelcontextprotocol.io/specification/2026-07-28
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.1.1
- https://pypi.org/project/mcp/2.1.1/
