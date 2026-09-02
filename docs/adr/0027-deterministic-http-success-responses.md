# ADR 0027 — Deterministic HTTP Success Responses

- Status: Proposed
- Date: 2026-09-02
- Tracking: GitHub Issue #115

## Context

Core exposes protocol-neutral `Success` and `Failure` outcomes. The HTTP
adapter must turn successful values into ASGI events without placing status
codes, media types, JSON rules, or server messages in core. Failure mapping is
separately security-sensitive and belongs to the RFC 9457 work in E6.5.

Starting a response before validating and encoding its complete non-streaming
value can leave the server unable to replace a partial or invalid response.
Response serialization therefore needs a fail-before-start boundary and an
explicit initial media contract.

## Decision

The first HTTP output boundary accepts `Success` only. A non-`None` value is
recursively projected to JSON-native data, encoded as deterministic compact
UTF-8 JSON, and represented by:

- status `200`;
- `content-type: application/json; charset=utf-8`;
- an exact byte `content-length`;
- one terminal `http.response.body` event.

Mappings require string keys. Lists and tuples become arrays. Dataclasses use
declared field order before deterministic key sorting, and enums recurse
through their value. Non-finite floats, bytes, arbitrary objects, and cyclic
graphs fail before `http.response.start`.

`Success(None)` produces status `204`, no representation headers, and an empty
terminal body event. For `HEAD`, serialization computes the same status and
headers as the equivalent request while the sender transmits no body bytes.

The sender emits exactly one `http.response.start` and then one terminal
`http.response.body`. It does not catch server errors or cancellation.
Canonical `Failure` is rejected explicitly until E6.5 supplies the reviewed
status and RFC 9457 representation mapping.

## Consequences

- JSON output behavior is reproducible and dependency-free.
- Invalid complete values cannot fail after response start.
- Dataclass and enum application outputs need no HTTP-aware base class.
- This boundary buffers the complete representation. Streaming and partial
  failures require a separate semantic design.
- Binary bodies, custom statuses/headers, redirects, files, alternative media
  types, and content negotiation remain unsupported rather than guessed.

## Guardrails

- No HTTP or JSON serialization type enters `agnara-core`.
- Failure messages/details are never serialized by this success boundary.
- `204` carries no representation metadata.
- `HEAD` suppresses bytes without rewriting the GET-equivalent length.
- All value traversal and encoding completes before the first ASGI event.
