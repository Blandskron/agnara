# ADR 0044 — MCP Tool Invocation Dispatch

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #185 (E7.8b)

## Context

Discovery (E7.4), the authorization bridge (E7.5), interaction projection
(E7.6) and result projection (E7.8a) are each complete and independently
tested, but no code connects them: `tools/call` still answers
`METHOD_NOT_FOUND`. E7.9 cannot benchmark invocation that does not exist, and
the conformance matrix cannot claim a tool surface that cannot be called.

Two facts constrain the design. Declared `scopes` are metadata and authorize
nothing on their own (ADR 0008), so a compiled plan carries no scope policy
unless an application attached one. Discovery already filters the tool list by
those declared scopes, which is visibility rather than authorization
(`AGENTS.md`). Connecting invocation without closing that gap would let a
caller execute a capability that its own `tools/list` response hides.

## Decision

The adapter exports `McpToolInvoker`, `build_mcp_server` and
`McpInvocationDefinitionError`. `McpToolInvoker` compiles one immutable route
table at construction — exposure name to compiled plan plus one core
`ScopePolicy` built from that capability's declared scopes — and dispatch does
a mapping lookup, one authorization evaluation, one `invoke_result` call and
one `project_mcp_result` call. It holds no per-request state, so one instance
serves every concurrent request on a connection.

The invoker enforces declared scopes with core's own `ScopePolicy` before any
dependency is resolved or handler runs. That guard runs first and never
replaces plan policies: a capability that also attached policies keeps them,
and core evaluates them inside `invoke_result` as usual. The adapter therefore
adds no policy semantics of its own; it applies an existing core policy to a
declaration the transport already treats as meaningful.

Protocol errors and capability failures stay separate. An unknown tool name,
task-augmented execution and any attempt to resume a call raise `MCPError`
with `INVALID_PARAMS`, because there is no call to make. Everything else —
invalid input, denial, timeout, redacted handler exceptions, interaction
requirements — is a canonical outcome projected by E7.8a, so a caller and its
model can see and correct it.

Resumption is refused rather than ignored. `requestState` and `inputResponses`
have no verification path (ADR 0042), so accepting either would be accepting
unverified confirmation evidence.

A caller-supplied argument naming a dependency or `ExecutionContext`
parameter is answered with core's own `invalid_input` message for an
undeclared input, so runtime-owned parameter names stay unpublished and a
forged one is indistinguishable from a typo. An optional server `timeout`
becomes the invocation deadline, producing a canonical `timeout` failure.
Cancellation is never converted into a result: an abandoned request propagates
so the SDK drops it and core unwinds dependency cleanup.

`build_mcp_server` reuses the discovery builder, so discovery keeps its frozen
snapshot, private zero-TTL results and absent pagination, and a name can never
be discoverable through one surface and unknown to the other.
`build_mcp_discovery_server` remains available and remains discovery-only; its
advertised capabilities follow the handlers actually registered.

## Alternatives

- Trust core policies alone: rejected because declared scopes attach no
  policy, so a capability hidden from `tools/list` would still execute.
- Filter invocation by the discovery visibility set: rejected because that
  makes hiding into authorization and reports a denial as a missing tool.
- Map denials and invalid input to JSON-RPC errors: rejected for the reason
  ADR 0043 already records — canonical failures are tool results.
- Compile a fresh `ExecutionPlan` per call: rejected because plans are
  immutable startup artifacts and per-call reflection is the cost E4.3 removed.
- Answer resumption by ignoring the extra fields: rejected because silently
  discarding forged confirmation state reads as acceptance.

## Evidence and limits

`tests/mcp/test_tool_invocation.py` drives the dispatcher directly for
success, defaults, invalid input, unknown names, refused task and resumption
params, scope denial, forged runtime-owned parameters, dependency lifecycle,
redaction, unrepresentable values, deadlines, cancellation and concurrency.
`tests/mcp/test_sdk_conformance.py` repeats the surface through the official
`Client`, including authorization parity with discovery, protocol errors,
a server deadline and client abandonment.

This is invocation evidence, not complete MCP conformance. Output schemas,
progress notifications, structured content negotiation, MRTR resumption,
Tasks, network transports and invocation benchmarks (E7.9) remain out of
scope. No version, tag or release changes here.
