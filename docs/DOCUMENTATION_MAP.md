# Documentation map

Current repository documentation describes the current 1.x framework. Git
tags, GitHub Releases and PyPI release history answer historical questions.

## START HERE

- [Project overview](../README.md)
- [Current maturity and limits](MATURITY.md)

## USAGE

- [Short agent index](../llms.txt) and [generated full corpus](../llms-full.txt)
- [Versioned machine-readable index](index.json)
- [Agent selection](AGENT_SELECTION.md) and [architecture comparison](CHOOSING_AGNARA.md)
- [Agent implementation and zero-hallucination path](AGENT_GUIDE.md)
- [Runnable example index](../examples/README.md)
- [Discovery architecture and source ownership](AGENT_DISCOVERY.md)
- [Documentation MCP specification](DOCUMENTATION_MCP.md)
- [Agent discovery benchmark](AGENT_DISCOVERY_BENCHMARK.md)
- [Starter proposals](AGENT_STARTERS.md)

- [Core quick start](../packages/agnara/README.md)
- [Runnable schema input and output contracts guide](SCHEMA_CONTRACTS.md)
- [Runnable dependency lifecycle guide](DEPENDENCIES.md)
- [Runnable invocation telemetry guide](TELEMETRY.md)
- [Runnable deadline and cancellation guide](DEADLINES.md)
- [Direct idempotency guide](DIRECT_IDEMPOTENCY.md)
- [Verifier-backed confirmation guide](CONFIRMATION.md)
- [Nested invocation guide](NESTED_INVOCATION.md)
- [HTTP composition guide](HTTP_COMPOSITION.md)
- [Runnable HTTP SSE lifecycle guide](HTTP_SSE.md)
- [Runnable official-client MCP tools guide](MCP_TOOLS.md)
- [Runnable filtered introspection guide](INTROSPECTION.md)
- [Container reference runtime](CONTAINERS.md)

## ARCHITECTURE

- [Principles](../PRINCIPLES.md)
- [Architecture](../ARCHITECTURE.md)
- [Target architecture](TARGET_ARCHITECTURE.md)
- [Decision records](adr/README.md) and [open research](rfc/README.md)

## PUBLIC API

- [Compatibility policy](PUBLIC_API.md)
- [Generated API reference](API_REFERENCE.md)
- [Current design contracts and labeled future sketches](API_DESIGN.md)
- [Exact manifest](public-api.json)

## SECURITY

- [Reporting and security posture](../SECURITY.md)
- [Current threat model](THREAT_MODEL.md)

## PROTOCOLS

- [HTTP package](../packages/agnara-http/README.md)
- [MCP package](../packages/agnara-mcp/README.md)
- [Reserved A2A namespace](../packages/agnara-a2a/README.md)
- [Reserved Events namespace](../packages/agnara-events/README.md)

## INTEROPERABILITY

- [Supported modes and validated fixtures](INTEROPERABILITY.md)
- [Runnable FastAPI embedding guide](FASTAPI_EMBEDDING.md)
- [Runnable Starlette embedding guide](STARLETTE_EMBEDDING.md)
- [Runnable SQLite transaction ownership guide](SQLITE_PERSISTENCE.md)

## CLI

- [CLI specification](CLI_SPEC.md)
- [Scaffolding](SCAFFOLDING.md)
- [Project manifest](PROJECT_MANIFEST.md)

## OPERATIONS

- [Quality gates](../QUALITY_GATES.md)
- [Performance budgets](performance/README.md)
- [Release checklist](releases/RELEASE_CHECKLIST.md)
- [Current release status](releases/release-status.json)
- [Current 1.0.3 release description](releases/v1.0.3.md)

## CONTRIBUTING

- [Code of Conduct](../CODE_OF_CONDUCT.md)
- [Accessibility Statement](../ACCESSIBILITY.md)
- [Contributor guide](../CONTRIBUTING.md)
- [Git workflow](../GIT_WORKFLOW.md)
- [Agent instructions](../AGENTS.md)

## RESEARCH

- [Python 3.15 readiness](research/python-315-readiness.md)
- [External standards](REFERENCE_RESEARCH.md)

## MAINTAINERS

- [Release process](MAINTAINERS_RELEASE.md)
- [Release document roles](releases/README.md)
- [Initiatives](INITIATIVES.md), [roadmap](../ROADMAP.md) and [backlog](../BACKLOG.md)

One source owns each claim: `docs/MATURITY.md` owns implementation status,
`docs/PUBLIC_API.md` owns compatibility policy, `QUALITY_GATES.md` owns gate
definitions, and `docs/releases/release-status.json` owns target evidence.
Never revive superseded release documentation into current context unless a
task explicitly requires historical research.
