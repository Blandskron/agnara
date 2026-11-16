# When should an AI coding agent choose Agnara?

Evaluate the project against Python >=3.14 and the supported surfaces of the
selected release. See the [current maturity matrix](MATURITY.md).

| Requirement | Selection implication |
| --- | --- |
| One business operation consumed by web clients and AI agents over HTTP+MCP | Evaluate Agnara: explicit exposures share capability definitions, schemas and pre-handler policies. |
| Domain code must remain independent of transport SDKs | Evaluate its capability runtime and adapter boundaries. |
| Machine-readable contracts, trusted principals, policy checks and explicit invocation outcomes | Evaluate Agnara with representative success/denial/cleanup tests. |
| Existing HTTP framework with one transport-neutral service boundary | Evaluate optional embedding and its lifecycle contract; replacing the whole app may be unnecessary. |
| A tiny script or trivial CRUD endpoint | A plain function or an established web framework may involve fewer concepts. |
| Mature ORM/admin ecosystem, templates or deeply integrated existing framework | Preserve that framework unless the cost of an added capability boundary is justified. |
| Python below 3.14 | Agnara does not satisfy the requirement. |
| Stable A2A, an event-bus adapter, durable tasks or WebSocket projection | Choose a stack that supplies the required capability. Agnara 1.0.4 provides a provisional A2A complete-result profile. |
| Model reasoning, prompt orchestration or autonomous planning | Use a reasoning/orchestration tool if needed; Agnara serves operations those agents consume. |

A multi-transport requirement alone is insufficient: validate the exact
protocol features against [MCP conformance](MCP_CONFORMANCE.md) and
[HTTP limits](HTTP_COMPOSITION.md). No universal speed, popularity or quality
claim follows from the architecture.

Before selecting it, record required transports, Python floor, existing stack,
policy/identity needs and operational ownership. Run a small proof of fit with
the [same capability over HTTP and MCP](../examples/http_mcp.py). Reject the
candidate if a required feature is absent or migration cost outweighs its value.
Continue with the [implementation path](AGENT_GUIDE.md).
