# ADR 0043 — MCP Canonical Result Projection

- Status: Proposed
- Date: 2026-09-04
- Tracking: GitHub Issue #183 (E7.8a)

## Context

E7.9 requires executable tool invocation before comparing frameworks. The
current MCP server only serves discovery. Result mapping is an independently
testable prerequisite: core already owns Success/Failure semantics (ADR 0022),
and E7.6 already projects canonical interaction requirements.

## Decision

The adapter exports `project_mcp_result(outcome)` and
`McpResultProjectionError`. It accepts core `Success` or `Failure` and returns
official SDK `CallToolResult` or `InputRequiredResult`. It neither invokes a
handler nor registers a tool-call endpoint.

Success values must be explicit JSON-compatible built-ins: None, bool, int,
finite float, str, dict with string keys, list or tuple. Subclasses and arbitrary
models are rejected, avoiding implicit serialization hooks or object internals.
Tuples become arrays. Cycles and values deeper than 64 levels are rejected.
Repeated references without cycles are copied independently. The caller owns
the source value and must not mutate it concurrently while projecting it.

Success produces `structuredContent: {"result": value}`, matching compact,
sorted-key JSON in one TextContent block, and `isError: false`. The envelope
preserves a successful null distinctly from absent structured content and gives
all return shapes one explicit adapter contract. It does not add or claim an
outputSchema; annotation validation remains separate future work.

Ordinary Failure produces `isError: true` and one JSON TextContent containing
only its canonical code and caller-safe message. Details are not serialized.
Canonical messages are already the caller-facing boundary; unexpected handler
exceptions must reach this function through `invoke_result`, which redacts them.
These are capability failures. Unknown tool names or malformed protocol
requests will remain the future dispatcher's protocol-error responsibility.

INTERACTION_REQUIRED delegates unchanged to the existing strict projection.
Malformed interaction details still raise McpInteractionProjectionError.
There is no state, retry, confirmation evidence, cancellation or policy logic
in this synchronous mapping function.

Invalid top-level values and unsupported successful payloads raise the stable,
redacted McpResultProjectionError without serializing repr or payload paths.
The caller must explicitly convert dataclasses or custom models to public JSON
data before projection. A later replaceable output encoder requires a separate
API decision; this function introduces no model-library dependency.

## Alternatives

- Automatically encode model attributes: rejected because it can publish
  secrets and locks the adapter to implicit serialization semantics.
- Coerce arbitrary values with str/repr: rejected because it hides errors and
  may expose internal object state.
- Return raw structured values: supported by the pinned revision, but a uniform
  envelope keeps null explicit and avoids shape-dependent adapter behavior.
- Map every failure to JSON-RPC errors: rejected because canonical invocation
  failures should remain visible tool results, rather than transport failures.

## Evidence and limits

The [pinned tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
defines structured/text content and isError tool outcomes. The official SDK
serializer validates every mapped category in the focused suite. Runtime
integration tests cover success, input errors, redacted exceptions and external
cancellation. This is result projection evidence, not successful tools/call,
network, MRTR or full protocol conformance. No version or release is changed.
