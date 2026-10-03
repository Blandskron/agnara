# Discovering and calling MCP tools

Declare a capability once, select its MCP exposure explicitly, and invoke it
through an official SDK server built from its compiled plan. Discovery does
not grant authorization to execute a tool.

## Run the example

From the repository root with Python 3.14:

```bash
uv sync
uv run python examples/mcp_tools.py
```

The complete [example](../examples/mcp_tools.py) needs the workspace's pinned
`mcp==2.1.1` SDK. It connects the official `Client` to an in-process server and
uses no sockets, external service or credentials. Its output is:

```text
protocol: 2026-07-28
tools: ['catalog.total', 'catalog.broken']
valid: 30
invalid_input: invalid_input
forged_dependency: invalid_input
denied: forbidden
handler_failure: internal_failure
unknown_tool: protocol_error (-32602)
recovered: 10
effects: ['resource.open', 'total:3:10', 'resource.close', 'resource.open', 'broken.handler', 'resource.close', 'resource.open', 'total:1:10', 'resource.close']
```

The long final line is a local lifecycle record, not MCP output. Invalid,
forged, denied and unknown requests run before those effects and leave it empty.

## Compile the application and exposures

The example declares a public `total` capability, a scoped `private` capability
and a deliberately failing `broken` capability. `Ledger` is an invocation-owned
dependency with async generator teardown, not a caller argument.

The composition root selects MCP exposures, freezes capabilities and compiles
their execution plans. The server does not compile plans implicitly:

```python
from agnara.execution import ExecutionPlan
from agnara_mcp import Mcp, McpAuthorization, build_mcp_server

mcp = Mcp(app, surface="agents")
mcp.tool(total)
mcp.tool(private)
mcp.tool(broken)
capabilities = app.compile()
exposures = mcp.compile()
plans = [ExecutionPlan.compile(definition, dependencies) for definition in capabilities.values()]
server = build_mcp_server(
    exposures,
    plans,
    container,
    name="catalog-example",
    version="demo",
    authorization=McpAuthorization(exposures, reject_authenticated),
    timeout=2,
)
```

This excerpt uses the application, dependency registry, container and mapper
explicitly defined in the example. All Agnara imports use governed public
paths. MCP stays an adapter rather than the meaning of a capability.

## Inspect discovery and outcomes

The official client negotiates exactly the pinned MCP revision. The anonymous
list contains the two public tools in declaration order. `catalog.private`
requires `catalog:read`, so it is omitted; calling it by its known name still
returns `forbidden` before dependencies or the handler run.

Discovery returns detached, private, zero-TTL results without a next cursor.
The `total` input schema is a closed object containing `quantity` and optional
`unit_price`; `Ledger` is excluded. Omitting `unit_price` uses the compiled
Python default of 10. The adapter does not publish that default as a JSON Schema
`default` property. Supplying an argument called `ledger` is rejected as an
undeclared caller input.

Successful results have `is_error == False`, a `structured_content` result
envelope and equivalent JSON text. Invalid input, scope denial and handler
failure have `is_error == True` with caller-safe JSON code/message data.
Unexpected exception diagnostics are redacted; the fixture's synthetic
`demo-private-diagnostic` never reaches the caller.

An unknown name instead raises the SDK's `MCPError` with `INVALID_PARAMS`.
It is not a capability outcome because no tool exists to invoke. The example
catches this protocol error, then successfully calls a known tool. It also
calls that tool again after the deliberately failing handler, demonstrating
that these errors do not destroy the connection.

The declarations use `output=...`, which the core validates before successful
values leave execution. MCP `outputSchema` is still absent: core validation
and protocol schema publication are separate contracts. See ADR 0086.

## Own identity and lifecycle

This is an anonymous tutorial. Its mapper deliberately rejects every
authenticated identity instead of inventing authorization. It never sets a
verified-token ContextVar or treats tool arguments as a credential.

For an authenticated deployment, a host must verify tokens and configure its
trusted mapper from the adapter's credential-free `McpAuthenticatedIdentity`
facts to an Agnara `Principal`. The mapper must decide actor, subject and
delegation semantics explicitly. Neither this example nor the in-process
connection tests OAuth verification.

The `Client` async context manager owns its connection work. The application
closes `DIContainer` in `finally` after the client exits; invocation providers
already close after success or handler failure. A server invocation deadline
and an overall demonstration timeout bound the run. Tests assert that no task
survives it and that the script works from outside the checkout.

## Evidence limits

The modern SDK in-process connection uses a direct dispatcher pair. This
example exercises SDK discovery, invocation and result validation; it does
not test sockets, JSON-RPC framing, HTTP or stdio transport. It adds no
network deployment command or authentication server.

The supported subset has no MCP stream projection, Tasks, MRTR resumption,
resources/prompts, replay or `outputSchema` contract. A reconnect, confirmation
form or caller-supplied state does not gain those semantics. The
[MCP conformance matrix](MCP_CONFORMANCE.md) owns the precise tested subset and
exclusions; the [package guide](../packages/agnara-mcp/README.md) owns the
adapter composition API.
