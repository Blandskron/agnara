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
schema mapping and discovery are implemented. Authorization,
interaction-required outcomes, Tasks/MRTR behavior and official SDK
conformance remain separate backlog items. Legacy protocol revisions are not
advertised until Agnara has explicit compatibility tests for them, even though
the SDK can serve older clients.

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
from agnara_mcp import build_mcp_discovery_server, project_mcp_tools

projected = project_mcp_tools(tools, plans)
server = build_mcp_discovery_server(
    projected,
    name="users",
    version="1.0.0",
    instructions="Use these tools only with an authorized caller.",
)
```

The server implements the modern `server/discover` and `tools/list` surfaces.
It advertises only MCP `2026-07-28` and the tools capability, with no mutable
list notifications. Tool discovery returns the complete frozen startup
snapshot in declaration order, so it emits no cursor and rejects any supplied
cursor as invalid parameters. Responses are detached from the startup state
and explicitly use `ttlMs: 0` with `cacheScope: private`.

Those cache settings are deliberately conservative. E7.5 will define
principal-aware authorization and filtering; discoverability and cache scope
must never be treated as authorization. This discovery-only server does not
implement `tools/call` and must not be presented as a complete MCP application
server.
