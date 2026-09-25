# Roadmap

Agnara's current foundation is the Python 3.14 capability runtime with explicit
HTTP, MCP, CLI and telemetry distributions. The [maturity matrix](docs/MATURITY.md)
records what is implemented and where the boundaries stop.

The canonical current-state source is `docs/MATURITY.md`.

## Direction

1. **Ecosystem validation.** Keep the existing standalone, hosted, embedded and
   side-by-side conformance lanes current as host libraries evolve.
2. **Learning and reference ecosystem.** Improve runnable guides and reference
   applications against the governed public API.
3. **Interoperability expansion.** Investigate new hosts, stores and protocol
   projections only after a contract, tests and an owner are defined.
4. **Python runtime research.** Evaluate Python 3.15 and free-threaded execution
   as separate evidence programs before changing support claims.
5. **Framework evolution.** Preserve the transport-neutral kernel while
   considering narrowly scoped capabilities through RFCs and reviewed issues.

A2A and events remain reserved namespaces. They do not imply protocol support.
GraphQL, gRPC, durable execution and broader MCP features are research or
separate future decisions, not current commitments. See
[initiatives](docs/INITIATIVES.md), [backlog](BACKLOG.md) and
[interoperability](docs/INTEROPERABILITY.md).

No delivery date or release cadence is implied by this roadmap.
