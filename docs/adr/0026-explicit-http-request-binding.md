# ADR 0026 — Explicit HTTP Request Binding

- Status: Proposed
- Date: 2026-09-02
- Tracking: GitHub Issue #113

## Context

One capability input can plausibly arrive through a path capture, query
parameter, header, or request body. Inferring the source from HTTP method,
parameter name, or annotation creates ambiguous behavior and makes generated
contracts difficult to keep deterministic. HTTP also needs wire conversion,
while ADR 0025 requires semantic validation to remain in the shared core path.

ASGI supplies raw query and header bytes and a streamed request body. Binding
therefore needs explicit decoding, resource limits, duplicate rules, and
cancellation behavior before response/error mapping is implemented.

## Decision

The HTTP adapter compiles an explicit source for every required ordinary
capability input. A binding names exactly one of path, query, header, or body;
an input cannot have multiple sources, two inputs cannot claim the same source
name, every route capture must be bound, and only one JSON body input is
supported. Optional handler inputs may remain unbound and use their defaults.

Path, query, and header bindings accept scalar schemas only. The adapter
converts HTTP text to strict string, integer, finite number, boolean, or binary
values described by the compiled schema. Missing values remain absent for core
required/default handling. Duplicate scalar values fail instead of silently
choosing first or last. Header names are ASCII tokens and lookup is
case-insensitive. Query names and values use strict percent decoding followed
by strict UTF-8; `+` represents space.

A body binding requires exactly one `application/json` content type, reads
ASGI `http.request` chunks up to a positive configured byte limit, propagates
cancellation, treats disconnect as a binding failure, decodes UTF-8 strictly,
and rejects malformed JSON, duplicate object keys, and non-finite numeric
constants. When no body is bound, the adapter does not call `receive`.

Binding returns plain invocation payload data. `ExecutionPlan` performs the
authoritative capability schema validation afterward. HTTP status and RFC 9457
serialization remain separate adapter decisions.

## Consequences

- Binding and generated HTTP contracts can share deterministic compiled
  source metadata without handler-signature inference on the request path.
- Direct, task, MCP, A2A, and HTTP invocation retain one semantic validation
  boundary.
- Repeated scalar query/header values are intentionally rejected; collection
  bindings require a later explicit design.
- This first body contract supports JSON only. Forms, multipart, files,
  streaming application inputs, cookies, and content negotiation require
  separate reviewed work.

## Guardrails

- No HTTP source concept enters `agnara-core`.
- No request body is read without an explicit body binding.
- Size checks occur while chunks arrive, before concatenation or JSON parsing.
- Malformed ASGI events become adapter binding failures; task cancellation is
  never translated.
