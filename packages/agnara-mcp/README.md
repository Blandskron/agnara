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
