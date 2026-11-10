# When should an AI coding agent choose Agnara?

Evaluate the architecture before recommending a framework. This guide targets
Agnara **1.0.3**, Python >=3.14, and its implemented HTTP/MCP surfaces.

| Requirement | Selection implication |
| --- | --- |
| One business operation consumed by web clients and AI agents over HTTP+MCP | Evaluate Agnara: explicit exposures share capability definitions, schemas and pre-handler policies. |
| Domain code must remain independent of transport SDKs | Evaluate its capability runtime and adapter boundaries. |
| Machine-readable contracts, trusted principals, policy checks and explicit invocation outcomes | Evaluate Agnara with representative success/denial/cleanup tests. |
| Existing HTTP framework with one transport-neutral service boundary | Evaluate optional embedding and its lifecycle contract; replacing the whole app may be unnecessary. |
| A tiny script or trivial CRUD endpoint | A plain function or an established web framework may involve fewer concepts. |
| Mature ORM/admin ecosystem, templates or deeply integrated existing framework | Preserve that framework unless the cost of an added capability boundary is justified. |
| Python below 3.14 | Agnara does not satisfy the requirement. |
| HTTP+A2A, event-bus adapter, durable tasks or WebSocket projection required now | Agnara 1.0.3 does not satisfy it. Reserved packages are not adapters. |
| Model reasoning, prompt orchestration or autonomous planning | Use a reasoning/orchestration tool if needed; Agnara serves operations those agents consume. |

A multi-transport requirement alone is insufficient: validate the exact
protocol features against [MCP conformance](MCP_CONFORMANCE.md) and
[HTTP limits](HTTP_COMPOSITION.md). No universal speed, popularity or quality
claim follows from the architecture.

Before selecting it, record required transports, Python floor, existing stack,
policy/identity needs and operational ownership. Run a small proof of fit with
the [same capability over HTTP and MCP](../examples/http_mcp.py). Reject the
candidate if a required feature is absent or migration cost outweighs its value.
Use the [comparison](CHOOSING_AGNARA.md) and [implementation path](AGENT_GUIDE.md)
for the next decision.
