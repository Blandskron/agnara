# MCP conformance evidence

Suite revision: 2. Tracking: [#181](https://github.com/Blandskron/agnara/issues/181)
and [#183](https://github.com/Blandskron/agnara/issues/183).

This is Agnara-owned compatibility evidence against the official `mcp==2.1.1`
and `mcp-types==2.1.1` packages for MCP `2026-07-28`. It is not an official
certification or a claim of complete MCP support.

## Reproduce

On Python 3.14, from the workspace:

```bash
uv sync --locked
uv run pytest tests/mcp tests/architecture
```

The normal CI pytest matrix collects these tests on Windows, Linux and macOS.
The suite requires neither network services nor credentials at execution time.
Dependency installation still requires the locked packages to be available.

## Measurement boundary

`test_sdk_conformance.py` compiles real Agnara capabilities, projects their
input schemas, builds the discovery server, and connects the official
`Client(..., mode="auto")`. The client negotiates the exact pinned modern
revision; the discovery contract test asserts it explicitly. Requests traverse
the official ClientSession, modern dispatcher, server validation and result
validation. No adapter handler is called directly.

The SDK's in-process modern connection uses a direct dispatcher pair. It does
not exercise sockets, HTTP, stdio or JSON-RPC framing. Generic official
`Request` models allow malformed pagination and unsupported methods to reach
server dispatch instead of being rejected by a typed client constructor.

## Coverage matrix

| Surface | Executable evidence | Limit |
| --- | --- | --- |
| Discovery | `test_sdk_conformance.py`, `test_discovery.py`: pinned revision, tools-only advertisement, server identity, private zero-TTL results | No legacy compatibility claim |
| Tool definitions | `test_schema_mapping.py`, `test_tool_projection.py`, `test_sdk_conformance.py`: compiled inputs, closed schemas, stable names and no output/task claims | Output validation and invocation are absent |
| Pagination errors | `test_sdk_conformance.py`: empty/unissued cursors and malformed numeric/list cursors return `INVALID_PARAMS`; discovery still works afterward | Complete startup snapshot, no pagination implementation |
| Authorization isolation | `test_sdk_conformance.py`: concurrent anonymous, unscoped and scoped tasks share one client; private lists change with each request identity and remain detached | SDK verified identity context is supplied by the test; OAuth verification is not tested |
| Authorization failures | `test_authorization.py`: immutable credential-free mapper input, fail-closed mapper errors and scope filtering | Discovery visibility does not authorize invocation |
| Unsupported calls | `test_sdk_conformance.py`: tool calls, resource/prompt lists and task methods return `METHOD_NOT_FOUND`, with no handler effects and recovery afterward | No successful `tools/call`, resources, prompts or Tasks implementation |
| Forged resumption | `test_sdk_conformance.py`: unsupported tool invocation remains rejected even with echoed state and an accepted confirmation form | Does not validate an MRTR security boundary; no resumption path exists |
| Canonical interaction | `test_interaction_mapping.py`: real pre-effect core failure projects to official input-required models, with deterministic serialization and rejection of malformed details | One-way projection only; no verifier-backed round trip |
| Canonical results | `test_result_projection.py`: SDK-validated success and every failure category; detached JSON/text, malformed/cyclic/deep value rejection, runtime exception redaction and cancellation propagation | Projection only; no successful tool-call dispatcher or outputSchema validation |
| Tasks/MRTR boundary | `test_task_boundary.py`: pinned SDK method inventory, carrier set, no task advertisement or exported resumption API | No state sealing, verification, replay store or Tasks extension |

The concurrency test uses owned `TaskGroup` tasks and a barrier, with a bounded
scenario timeout. It leaves the client's default cache policy enabled, so
accidental reuse of authenticated discovery by anonymous calls can fail the
test. Each task resets its authentication ContextVar in `finally`.

## Explicit exclusions

Network transport conformance, OAuth token verification, complete protocol
certification, legacy revisions, successful tool invocation, output contracts,
MRTR resumption, confirmation verification over MCP, Tasks, notifications,
streaming and performance remain outside this suite's support claim. Future
implementation must extend the matrix with positive and negative evidence
before those surfaces are advertised.

## Upstream reference

The pinned [official SDK source](https://github.com/modelcontextprotocol/python-sdk/tree/v2.1.1)
is the reference, particularly `src/mcp/client/client.py`,
`src/mcp/client/session.py` and `src/mcp/server/runner.py`. Agnara tests its
adapter through that boundary rather than reimplementing the SDK's validator.
