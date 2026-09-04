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
schema mapping, discovery, authorization, interaction-required outcomes,
Tasks/MRTR behavior and official SDK conformance remain separate backlog
items. Legacy protocol revisions are not advertised until Agnara has explicit
compatibility tests for them, even though the SDK can serve older clients.

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
