# agnara-mcp

Model Context Protocol exposure adapter. Owns MCP server projection, tool discovery, invocation dispatch, schema mapping and MCP authorization integration.

- Import package: `agnara_mcp`
- Depends on: `agnara-core`
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.

## Protocol baseline

The first adapter line targets exactly MCP `2026-07-28` through the official
Python SDK `mcp==2.1.1`. The public constants are:

```python
from agnara_mcp import MCP_PROTOCOL_VERSION, SUPPORTED_MCP_PROTOCOL_VERSIONS

assert MCP_PROTOCOL_VERSION == "2026-07-28"
assert SUPPORTED_MCP_PROTOCOL_VERSIONS == ("2026-07-28",)
```

This pin establishes the protocol boundary; it is not a claim that the
unfinished E7 adapter already implements every MCP feature. Tool projection,
schema mapping, discovery, the request-scoped authorization bridge, canonical
result and interaction-required projection, and `tools/call` dispatch are
implemented. MRTR resumption and Tasks behavior remain separate backlog work,
and invocation is not yet benchmarked. Bounded
official SDK compatibility evidence is recorded in
[`docs/MCP_CONFORMANCE.md`](../../docs/MCP_CONFORMANCE.md); it covers the
implemented surfaces and does not claim complete MCP conformance.
Legacy protocol revisions are not advertised until Agnara has
explicit compatibility tests for them, even though the SDK can serve older
clients.

## Tool exposures

Declare tool exposure separately from capability semantics:

```python
from agnara import Agnara
from agnara_mcp import Mcp

app = Agnara("users")
mcp = Mcp(app)


@app.capability
def get_user(user_id: str) -> str:
    return user_id


mcp.tool(get_user)
tools = mcp.compile()
```

The default MCP name is the stable capability identity (`users.get_user`).
Pass `name="users-get"` to select a different valid wire name. Compilation is
idempotent, closes registration, and returns an immutable snapshot in
declaration order. Exposure registration itself intentionally does not create
incomplete SDK `Tool` objects before execution plans and schemas are available.

Compile protocol-neutral execution plans, then project the frozen exposures to
official SDK definitions with `project_mcp_tools(tools, plans)`. Input schemas
are closed JSON Schema objects, preserve handler parameter order, and omit DI
and `ExecutionContext` parameters. Schema fragments are copied into detached
JSON data so mutating an SDK model cannot alter the core plan or a later
projection.

`outputSchema` is intentionally absent for now. Agnara will publish it only
after the core runtime compiles and validates output annotations; declaring an
unenforced response contract would make client validation unreliable.

## Discovery

Build a discovery-only official SDK server after exposure and plan compilation:

```python
from agnara.policy import Principal
from agnara_mcp import McpAuthorization, build_mcp_discovery_server, project_mcp_tools


def map_mcp_identity(identity) -> Principal:
    # The application explicitly decides whether client, subject, or both
    # represent its actor identity.
    actor = identity.client_id
    if identity.subject is not None:
        actor = f"{actor} acting-for {identity.subject}"
    return Principal(actor, scopes=identity.scopes)

projected = project_mcp_tools(tools, plans)
authorization = McpAuthorization(tools, map_mcp_identity)
server = build_mcp_discovery_server(
    projected,
    name="users",
    version="1.0.0",
    instructions="Use these tools only with an authorized caller.",
    authorization=authorization,
)
```

The server implements the modern `server/discover` and `tools/list` surfaces.
It advertises only MCP `2026-07-28` and the tools capability, with no mutable
list notifications. Tool discovery returns the complete frozen startup
snapshot in declaration order, so it emits no cursor and rejects any supplied
cursor as invalid parameters. Responses are detached from the startup state
and explicitly use `ttlMs: 0` with `cacheScope: private`.

`McpAuthorization` reads the official SDK's request-local verified access-token
context. Anonymous requests receive an `AnonymousPrincipal`; authenticated
requests pass only immutable, credential-free client, issuer, subject,
resource and scope facts to the application's explicit mapper. Bearer tokens
and arbitrary claims are never passed to it. The SDK token verifier remains
responsible for token validity, expiry, resource/audience and trust decisions.
The mapper is a trusted, request-safe application boundary and must explicitly
define actor/delegation semantics instead of assuming that an OAuth client and
subject are interchangeable.

`tools/list` includes an exposure only when all statically declared capability
scopes are present on the mapped principal. Results retain conservative
`ttlMs: 0` and `cacheScope: private` hints. This is visibility filtering, not a
substitute for policy evaluation at invocation time. `build_mcp_discovery_server`
serves discovery alone and answers `tools/call` with `METHOD_NOT_FOUND`; use
`build_mcp_server` when the same snapshot must also be invocable.

## Tool invocation

```python
from agnara.core.di import DIContainer
from agnara_mcp import build_mcp_server

server = build_mcp_server(
    tools,
    plans,
    DIContainer(registry),
    name="users",
    version="1.0.0",
    authorization=authorization,
    timeout=30,
)
```

Invocation is added over the discovery snapshot described above, so a name can
never be invocable without being discoverable. One immutable route table is
compiled at startup; a call does a mapping lookup, one authorization
evaluation, one core invocation and one result projection, and the dispatcher
keeps no per-request state.

Each call enforces that capability's statically declared scopes with core's
`ScopePolicy` before any dependency is resolved or handler runs. Declared
scopes authorize nothing on their own (ADR 0008) and discovery filtering is
visibility, so without this guard a caller could execute a capability its own
`tools/list` response hides. The guard never replaces the plan's own policies:
those still run inside the core runtime.

Protocol errors and capability failures stay separate. An unknown tool name,
task-augmented execution and any `requestState` or `inputResponses` are
`INVALID_PARAMS` errors, because there is no call to make and no verified
resumption path exists. Invalid input, denial, timeout, redacted handler
exceptions and interaction requirements are canonical outcomes projected as
tool results, so a caller and its model can see and correct them.

A caller-supplied argument naming a dependency or `ExecutionContext` parameter
is answered with the same `invalid_input` message an undeclared input receives,
so runtime-owned parameter names stay unpublished. The optional `timeout`
becomes the invocation deadline and yields a canonical `timeout` result.
Cancellation is never converted into a result: an abandoned request propagates
so the SDK drops it and core unwinds dependency cleanup. See ADR 0044.

## Canonical result projection

Convert the core runtime outcome with `project_mcp_result`:

```python
from agnara.execution import Success
from agnara_mcp import project_mcp_result

result = project_mcp_result(Success({"total": 42}))
# structuredContent: {"result": {"total": 42}}
# content: [{"type": "text", "text": '{"result":{"total":42}}'}]
```

Use `project_mcp_result(await invoke_result(plan, context))` in composition
code. Success accepts explicit JSON built-ins; tuples become arrays. Data is
copied, object keys are sorted in the equivalent JSON text, and a `result`
envelope preserves successful null. No outputSchema is claimed. Unsupported
objects, subclasses, non-string keys, non-finite numbers, cycles and nesting
beyond 64 levels raise `McpResultProjectionError` with a redacted message.
The caller owns the source value and must not mutate it during projection.

Ordinary canonical failures produce `isError: true` and JSON text with only
`code` and the caller-safe `message`; failure details are omitted. Application
code owns the safety of explicitly supplied canonical messages. Unexpected
exceptions are redacted by `invoke_result` before reaching this projection.
Interaction requirements delegate to the existing mapper described below.

This function serializes no arbitrary model fields and implements no
resumption. Dataclasses and custom models require explicit
conversion to public JSON data. See ADR 0043.

## Interaction-required projection

Project the adapter-facing canonical outcome rather than MCP values or
exception text:

```python
from agnara.execution import Failure, FailureCode, invoke_result
from agnara_mcp import project_mcp_interaction_required

outcome = await invoke_result(plan, context)
if isinstance(outcome, Failure) and outcome.code is FailureCode.INTERACTION_REQUIRED:
    mcp_result = project_mcp_interaction_required(outcome)
```

The currently supported `confirmation` kind becomes a 2026-07-28
`InputRequiredResult` containing one deterministic form-mode
`elicitation/create` request. Its restricted flat schema asks for one required
boolean field. The projection validates the complete canonical detail shape
but publishes neither capability identity nor arbitrary interaction hints.

This function only projects the interim result. It does not consume
`inputResponses`, create or verify `requestState`, or resume an invocation;
the dispatcher refuses both fields outright. An elicitation action or submitted boolean is untrusted
caller input and is never `ConfirmationEvidence` by itself. An application
confirmation verifier must independently bind and validate evidence before a
handler may run.

## Tasks and resumption

Tasks left the MCP core specification in `2026-07-28` and continue there as an
opt-in extension that the pinned SDK defines as types only and never
dispatches. Agnara neither implements nor advertises that extension, and its
tool projection never sets the legacy `execution.taskSupport` marker.

Multi Round-Trip Requests are the resumption mechanism of the pinned revision:
a client fulfills the `inputRequests` of an `InputRequiredResult` and retries
the same request with `inputResponses` and the echoed `requestState`. Nothing
in this package mints or accepts that state: the dispatcher rejects both fields
with `INVALID_PARAMS`.

When it does, three properties of the official boundary apply. `requestState`
is attacker-controlled until the SDK's `RequestStateBoundary` verifies it, and
because this package builds on the lowlevel `Server` rather than `MCPServer`
that middleware must be installed explicitly, with an explicit audience.
`RequestStateSecurity.ephemeral()` is process-local and rejects state minted
by another worker or before a restart, so a multi-instance deployment needs a
shared key ring. The envelope binds method, target, arguments, audience,
principal and expiry, but carries no single-use marker, so it is round
integrity rather than invocation replay protection.

A resumed round therefore re-evaluates the core policy and calls the
application confirmation verifier exactly as a first round does. See ADR 0042.
