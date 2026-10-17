# API design contract

This document records the constraints for public API changes. The
[public manifest](public-api.json) owns canonical exports and stability;
[maturity](MATURITY.md) owns implementation status. Use the
[runnable examples](../examples/README.md) for executable syntax.

## Authoring and composition

- An app represents a bounded context. A capability declares business intent;
  HTTP and MCP exposures are selected explicitly at composition.
- Compile declarations, schemas, dependencies and policies before invocation.
  Compiled registries and execution plans are immutable snapshots.
- Bind dependency types explicitly in `DIRegistry`. Handlers remain independent
  of transport SDKs; providers and containers have explicit lifecycle owners.
- Declare `output=...` for a checked result or stream unit. A return annotation
  alone does not establish an output contract. JSON conversion is an explicit
  schema boundary; direct Python invocation preserves Python values.
- Authenticate principals at a trusted host boundary. Scope, policy and
  confirmation checks precede dependency acquisition and handler effects.
  Risk/effect metadata and discoverability never grant authority.
- Invocation results and failures are protocol-neutral. Caller cancellation
  propagates; deadlines are cooperative and do not preempt synchronous work.
- Pull-based streams own producer and dependency cleanup. HTTP SSE projects
  that contract; another protocol needs its own reviewed projection.
- Nested complete-result invocation uses one compiled application snapshot,
  fresh child identity/context and independent policy/confirmation evaluation.
  Cross-application calls and delegated authority remain unsupported.
- Discovery is filtered before serialization. OpenAPI projects HTTP exposures;
  protocol-neutral introspection and optional human documentation remain distinct.
- Profiles select generated adapters, not different app runtime classes.
  Scaffolding is deterministic, supports dry-run and refuses overwrite by default.

These constraints follow [architecture](../ARCHITECTURE.md) and the
[decision records](adr/README.md). The implementation must not accidentally
create a second public API through internal modules or transport-specific types.

## Current usage references

Keep executable instructions in their owning guides instead of duplicating
partial examples here.

| Task | Canonical guide |
| --- | --- |
| Declare and invoke a capability | [Core quick start](../packages/agnara/README.md), [minimal runnable source](../examples/minimal_capability.py) |
| Input/output schemas and Python/JSON boundaries | [Schema contracts](SCHEMA_CONTRACTS.md) |
| Explicit providers and teardown | [Dependencies](DEPENDENCIES.md) |
| Confirmation with independently verified evidence | [Confirmation](CONFIRMATION.md) |
| Invocation deadlines and caller cancellation | [Deadlines](DEADLINES.md) |
| Execution telemetry | [Telemetry](TELEMETRY.md) |
| Same-snapshot nested invocation | [Nested invocation](NESTED_INVOCATION.md) |
| Explicit direct idempotency | [Direct idempotency](DIRECT_IDEMPOTENCY.md) |
| HTTP composition and documentation | [HTTP composition](HTTP_COMPOSITION.md) |
| HTTP streaming | [HTTP SSE](HTTP_SSE.md) |
| MCP discovery and invocation | [MCP tools](MCP_TOOLS.md), [conformance boundary](MCP_CONFORMANCE.md) |
| Filtered protocol-neutral discovery | [Introspection](INTROSPECTION.md) |
| Host-owned runtime composition | [Interoperability](INTEROPERABILITY.md) |
| Project/app generation and CLI output | [CLI specification](CLI_SPEC.md), [scaffolding](SCAFFOLDING.md), [manifest](PROJECT_MANIFEST.md) |

The [API reference](API_REFERENCE.md) lists classified exports; it is not a
replacement for executing a guide against the installed distribution versions.
Current-checkout evidence does not establish behavior in a historical wheel.

## Proposing new syntax

Compare the proposal with the current manifest, guides and architectural
constraints. Record undecided semantics in a scoped RFC and the accepted
contract in an ADR before implementation. Add a runnable example, compatibility
decision and relevant validation before publishing an export.

The [initiatives](INITIATIVES.md), [roadmap](../ROADMAP.md) and
[open RFC questions](rfc/README.md) track future work. They do not authorize
unsupported imports, decorators, constructors or CLI commands. Superseded API
sketches are available through Git history rather than the active usage path.
