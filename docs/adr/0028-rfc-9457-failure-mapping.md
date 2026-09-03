# ADR 0028 — RFC 9457 Failure Mapping

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #117

## Context

Core produces protocol-neutral `Failure` outcomes carrying a stable
`FailureCode`, a human-readable message and immutable details. ADR 0027
deliberately left the failure half of the HTTP output boundary unbuilt because
it is security-sensitive in ways success serialization is not:

- the HTTP status is itself an authorization signal, so guessing it leaks or
  misstates why a request was refused;
- `title`, per RFC 9457, must be occurrence-independent, so it cannot be the
  failure message;
- server-side failure text may contain internal context that a client must
  never see;
- a failure response is the server's last chance to answer, so it must not be
  the thing that fails.

## Decision

`FailureCode` is projected through one explicit, exhaustive table:

| `FailureCode`          | Status | `title`               |
| ---------------------- | ------ | --------------------- |
| `invalid_input`        | 400    | Invalid Input         |
| `unauthenticated`      | 401    | Unauthenticated       |
| `forbidden`            | 403    | Forbidden             |
| `not_found`            | 404    | Not Found             |
| `conflict`             | 409    | Conflict              |
| `interaction_required` | 428    | Interaction Required  |
| `rate_limited`         | 429    | Rate Limited          |
| `internal_failure`     | 500    | Internal Server Error |
| `unavailable`          | 503    | Service Unavailable   |
| `timeout`              | 504    | Timeout               |

`interaction_required` uses `428 Precondition Required` (RFC 6585): the
request was understood and refused only because it did not carry the
confirmation evidence the capability requires, and repeating it unchanged
cannot succeed. It is not `401`, because the principal is authenticated, and
not `403`, because the outcome is not a permanent denial. `timeout` uses `504`
rather than `408`, because the deadline that expired is the server-side
invocation deadline, not a wait for the client's request.

The response is `application/problem+json` with no media-type parameters, and
its document is the same deterministic compact UTF-8 JSON encoding ADR 0027
defined for success, including sorted keys and an exact `content-length`.
Members are:

- `type`: the compiled per-code problem URI, or `about:blank`;
- `title`: from the table above, never the failure message;
- `status`: from the table above, matching the response status;
- `detail`: the failure message, redacted for `internal_failure`;
- `code`: the `FailureCode` value, the stable machine-readable discriminator;
- `details`: the failure details, present only when non-empty;
- `instance`: present only when a dispatcher supplies a request target.

Agnara does not invent a hosted problem-documentation origin. Applications
compile an explicit absolute base URI at startup, which yields one kebab-case
type URI per code; with no base URI every problem keeps the RFC 9457 default
`about:blank` and remains machine-readable through `code`.

`Failure.details` is nested under a single `details` extension member rather
than spread across the top level. Extension members share the top-level
namespace with reserved members, and details originate from capability code,
so spreading them would let a detail key shadow `status`, `title` or `type`.

`internal_failure` never serializes the handler-supplied message or details.
Core already redacts unexpected exceptions, but a handler can return an
explicit `Failure(INTERNAL_FAILURE, ...)`, and this boundary is where that
text would leave the process.

Serialization completes before `http.response.start`, and an outcome that
cannot be represented raises instead of emitting a partial document. Because a
dispatcher must still answer, the module exposes one immutable, import-time
`internal_failure` response as the documented last resort.

## Consequences

- Status selection is reviewable in one place and cannot drift per capability.
- Adding a `FailureCode` without a reviewed status and title fails a test
  rather than silently defaulting to `500`.
- Clients get a stable machine-readable `code` even when the application
  publishes no problem documentation.
- Clients reading `details` must look one level down; the RFC-reserved
  `detail` string stays at the top level.
- `internal_failure` responses are intentionally uninformative to clients.
- `WWW-Authenticate` and `Retry-After` are absent. RFC 9110 requires the
  former with `401`, and `429`/`503` should carry the latter, but both need
  the authentication and rate-limit exposures Agnara has not designed yet.
  This is a documented gap, not a claim of HTTP conformance.
- Content negotiation, `problem+xml`, multi-error arrays and streaming
  failures remain unsupported rather than guessed.

## Guardrails

- No HTTP status, media type or problem-document type enters `agnara-core`.
- Status is never derived from `risk`, `effects` or `confirmation` metadata.
- `title` never varies per occurrence.
- `internal_failure` message and details never reach the wire.
- Failure details never shadow an RFC 9457 reserved member.
- The last-resort internal problem response is built at import and is
  therefore always available to a dispatcher.
