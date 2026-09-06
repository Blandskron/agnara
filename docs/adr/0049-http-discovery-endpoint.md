# ADR 0049 — The Authorized HTTP Discovery Endpoint

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #196 (E8.6)

## Context

E8.2 built the visibility layer and E8.3/E8.4 gave it a local consumer, where
the viewer is the operator reading their own source. E8.6 is the first surface
that serves a snapshot to someone else, which is the case the layer exists for.

Two facts make it different from every other surface in `agnara-http`. The
document is viewer-specific, so it cannot be precomputed bytes the way
`_HTTPSurface` serves OpenAPI and documentation UIs. And the package has no
authentication: `_HTTPDispatcher` documents that every invocation runs as the
anonymous principal, and that no path can produce a `401`.

RFC 0003 section 8 requires that viewer-specific documents be filtered before
projection and use correct cache controls and `Vary` semantics, that private
capabilities not be published automatically, and that viewing never authorize
invoking.

## Decision

`agnara_http._discovery` adds `_DiscoveryRoute`, `_compile_discovery` and
`_DiscoveryDispatcher`. The dispatcher wraps a fallback exactly as
`_SurfaceDispatcher` does, so composition order stays a chain rather than a
new concept, and every path it does not own is delegated unchanged.

**Authorization is a required argument, not a mode.** The route takes a
principal resolver — the application's authentication boundary; this package
verifies no credential and interprets no header. A resolver returning `None`
means "no identity this application recognises", which is not the same as
"allow anonymously": that is `allow_anonymous`, a separate flag defaulting to
`False`. Without it, an unidentified viewer gets `401`, and because RFC 9110
requires `WWW-Authenticate` on a `401`, an endpoint that can produce one must
declare its challenge at startup. An endpoint that opted into anonymous
discovery must *not* declare a challenge, because it can never answer `401`
and a dangling challenge would misdescribe it.

**A filtered document must never be reused across viewers.** `public`,
`s-maxage` and `immutable` are refused at startup rather than at request time,
because a shared-cacheable viewer-specific document is a configuration
mistake, not a runtime condition. The default is `private, no-store`: the
document is cheap to rebuild and expensive to leak. `Vary` is always sent and
must name at least one header, so the header stays correct if a composer later
relaxes the directive.

**Failure is closed and indistinguishable.** A resolver that raises, or
returns something that is not a `Principal`, produces the shared redacted
`500`. Neither is read as anonymous, and neither reports `401`, which would
invite a retry that cannot help. The client learns nothing about the
authentication boundary's internals.

`unauthenticated` joins `_TransportFailure`, reusing the code, status and
title the capability failure of the same name already has. `_problem_codes`
already documents that rule: where the semantics coincide, so does the code.

The path is static, has no default, and is reserved against every capability
route at startup — the same treatment `_HTTPSurface` gets, for the same
reason. `GET` and `HEAD` are served; anything else is `405` with `Allow`.

The body is the same `json_data()` document `agnara inspect --json` produces,
serialized compactly with sorted keys. The two wire forms differ only in
whitespace, which `tests/integration/test_discovery_consistency.py` asserts
by comparing the parsed documents across three visibility postures.

## Alternatives

- Precompute the document as an `_HTTPSurface`: rejected. It is viewer-
  specific, so there is no single set of bytes to precompute, and reusing the
  static path would make the leak silent.
- Default to anonymous discovery: rejected. RFC 0003 says the runtime must not
  guess an environment and silently publish private surfaces, and this is the
  surface that would.
- Report a resolver failure as `401`: rejected because a client would retry
  with the same credential and fail identically, and because it describes the
  server's state as the client's mistake.
- Validate cache directives at request time: rejected. A misconfiguration
  should fail the deployment, not the request that discovers it.
- Add an `ETag` and support conditional requests: deferred. It needs a
  per-viewer validator that cannot be confused across viewers, and that is a
  design decision this endpoint does not need in order to be correct.
- Reuse `FailureCode.UNAUTHENTICATED` directly: rejected because
  `_TransportFailure` deliberately is not `FailureCode`. Its docstring says a
  transport condition describes why no capability was reached; the shared
  `code` value is how the two stay legible to a client.

## Evidence and limits

`tests/http/test_discovery_endpoint.py` covers the explicit configuration
(no default path, authorization required, challenge presence and absence,
refused cache directives, `Vary`, static paths, capability-route conflicts,
type validation) and the serving behaviour (filtered per viewer, cache and
`Vary` headers, `401` with challenge, opt-in anonymous access, resolver
failure and a non-principal return, `HEAD`, `405` with `Allow`, delegation,
byte-identical repeat responses, and no runtime object in the body).
`tests/integration/test_discovery_consistency.py` proves the endpoint and the
CLI publish the same document.

Limits: no authentication scheme, no token verification, no rate limiting, no
audit logging, no conditional requests or `ETag`, and no public composition
API — this surface stays internal until the HTTP composition API is reviewed,
like every other surface in the package. Exposures still come from whoever
composes the snapshot; this endpoint contributes none.
