# ADR 0030 — Transport-Level HTTP Problems

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #129

## Context

ADR 0028 maps canonical `Failure` outcomes to RFC 9457 problems. It cannot
map the failures that happen before a capability runs: no route, a method the
target does not accept, a body over the limit, a media type the exposure does
not accept, request data that will not bind.

`FailureCode` has no member for "method not allowed" and should not gain one.
It describes what a capability decided; these describe why one was never
reached. Adding transport conditions to it would push HTTP semantics into
core, and MCP and A2A would inherit a status vocabulary that means nothing to
them.

`_binding.py` already detects every one of these conditions, but reported them
all as one error type with a free-text message. A dispatcher could only tell
"body too large" from "malformed JSON" by matching message text, which is not
a contract.

## Decision

Binding failures carry a reason, not just a message:

| `_BindingFailure`        | Transport failure   | Status |
| ------------------------ | ------------------- | ------ |
| `malformed`              | `invalid_input`     | 400    |
| `unsupported_media_type` | same                | 415    |
| `content_too_large`      | same                | 413    |
| `disconnected`           | none                | none   |

A disconnect has no status on purpose. There is nobody left to answer, so the
reason exists for a dispatcher to stop on.

Transport failures get their own reviewed table, parallel to the `FailureCode`
table and separate from it:

| `_TransportFailure`      | Status | `title`                |
| ------------------------ | ------ | ---------------------- |
| `invalid_input`          | 400    | Invalid Input          |
| `not_found`              | 404    | Not Found              |
| `method_not_allowed`     | 405    | Method Not Allowed     |
| `content_too_large`      | 413    | Content Too Large      |
| `unsupported_media_type` | 415    | Unsupported Media Type |

The document shape is the one ADR 0028 defined, so a client parses one format
regardless of how far the request got.

**Capability and transport failures share one problem-type namespace, keyed by
the `code` extension value.** `code` is what a client actually reads, and
where the semantics coincide so does the code: a capability reporting
`not_found` and a target with no route document the same thing. Codes that
exist only at the transport (`method_not_allowed`, `content_too_large`,
`unsupported_media_type`) are distinct.

RFC 9110 requires `Allow` on a `405`, so a problem response can carry required
headers. They are attached during serialization rather than at emission, so
the header cannot be forgotten by a code path that only knows how to send. An
added header may not shadow `content-type` or `content-length`, which the
response boundary owns.

## Consequences

- A dispatcher selects a status from a reason, never from message text.
- `405` cannot be emitted without `Allow`.
- Clients parse one problem format for every failure.
- `FailureCode` stays free of transport vocabulary, so MCP and A2A inherit
  nothing HTTP-shaped.
- Two tables must be kept consistent by review. They are deliberately not
  merged, because merging them is exactly the coupling this avoids.
- `401` and `429` are still absent: they need the authentication and
  rate-limit exposures that do not exist yet, and a status without its
  required challenge or retry header would be a false conformance claim.
- `406` and `Accept` handling remain out of scope; content negotiation is a
  separate decision.

## Guardrails

- No HTTP status or media type enters `agnara-core`.
- `FailureCode` never gains a transport-only member.
- Neither table is derived from `risk`, `effects` or `confirmation` metadata.
- A `disconnected` binding failure never produces a response.
- Added headers never shadow the representation headers.
