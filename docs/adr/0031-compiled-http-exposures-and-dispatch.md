# ADR 0031 — Compiled HTTP Exposures and Request Dispatch

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #131

## Context

E6.1 through E6.6a built every piece of an HTTP request path and no path.
`_HTTPDispatch` was a callable type nothing implemented; routing carried an
opaque target; binding plans were compiled separately with nothing tying a
route, a binding and an `ExecutionPlan` together. E6.7 asks for OpenAPI
generated "from compiled HTTP exposures", which did not exist.

## Decision

A declared exposure is a method, a path template, an `ExecutionPlan`, its
input bindings and a body limit. Compilation parses the template, compiles the
binding plan against the plan's real input schemas, registers the pair as the
route target, and freezes the registry. A matched route therefore resolves to
its plan and binding in one lookup, and every declaration error — a duplicate
route shape, an unbound path parameter, a binding for an unknown input, a
required input with no binding — is raised at startup.

Dispatch is one pass with no reflection: match, bind, invoke, serialize, send.

`HEAD` falls back to a `GET` exposure and suppresses only the body bytes, so
`content-length` still describes the `GET` representation. `Allow` on a `405`
therefore lists `HEAD` when a `GET` exposure exists and no explicit `HEAD` one
does, because the server does answer it.

`root_path` is stripped before matching, so a mounted application matches its
own paths rather than its mount prefix.

The problem `instance` carries the request path and **never the query string**.
A token or key passed in a query would otherwise be copied into the problem
body and into every log that retains it. A target that is not usable as a URI
reference yields no `instance` at all, rather than making a `404` fail to
serialize and become a `500`.

A client disconnect during the body read produces no response. There is
nobody to answer.

Serialization failure after invocation falls back to the prebuilt internal
problem from ADR 0028. Nothing has been sent at that point, so the fallback is
still available; this is the case that constant exists for.

Every invocation runs as the anonymous principal, which is also why no path
here produces a `401`. Authentication is undesigned, and a `401` without a
`WWW-Authenticate` challenge would be a false conformance claim.

## Consequences

- The adapter serves real requests, and E6.7 has a compiled exposure to
  project from.
- Malformed exposures cannot reach production; they fail at import or startup.
- The hot path holds no lock and performs no reflection.
- Exposures are declared explicitly. There is no decorator or composition API
  yet; that is E0A, and this deliberately does not guess it.
- Transport metadata on the invocation is three fields: transport, method,
  path. Anything richer would push HTTP vocabulary into core telemetry.
- Streaming, WebSockets, cookies, multipart, redirects, static files and
  content negotiation remain unimplemented rather than approximated.

## Guardrails

- No HTTP type enters `agnara-core`; the dispatcher builds `Invocation` and
  `ExecutionContext` and calls `invoke_result`.
- Exactly one `http.response.start` and one terminal body event per answered
  request, on every path including failures.
- `asyncio.CancelledError` propagates and never becomes a response.
- The problem `instance` never carries a query string.
- The registry a request path reads is frozen and shared without a lock.
