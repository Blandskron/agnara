# agnara-mcp

Model Context Protocol exposure adapter. Owns MCP server projection, tool discovery, schema mapping and MCP authorization integration.

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
schema mapping, discovery, the request-scoped authorization bridge and
canonical interaction-required projection are implemented. Tool invocation,
MRTR resumption, Tasks behavior and official SDK conformance remain separate
backlog work. Legacy protocol revisions are not advertised until Agnara has
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
substitute for policy evaluation at invocation time. This discovery-only
server does not implement `tools/call` and must not be presented as a complete
MCP application server.

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

This function only projects the interim result. It does not register
`tools/call`, consume `inputResponses`, create or verify `requestState`, or
resume an invocation. An elicitation action or submitted boolean is untrusted
caller input and is never `ConfirmationEvidence` by itself. An application
confirmation verifier must independently bind and validate evidence before a
handler may run; E7.7 will research the MRTR/state boundary.
