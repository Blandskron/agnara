# Proposed external starter projects

Status: proposals only. No external repositories, deployments or packages were
created. Start from existing CLI templates; avoid a second framework generator.
Each starter should pin synchronized **1.0.3**, require Python >=3.14 and pass
tests against installed wheels outside this framework checkout.

| Proposed repository | Smallest useful scope | Acceptance tests |
| --- | --- | --- |
| `agnara-backend-starter` | One bounded-context capability, dataclass input/output, explicit DI, HTTP ASGI composition, trusted identity integration seam | Direct and HTTP values, invalid input, scope denial before effects, lifespan cleanup; no built-in ORM claim. |
| `agnara-mcp-starter` | One read-only capability, explicit MCP tool exposure, host-owned container, fail-closed authenticated mapping seam and official-client fixture | Tool discovery/schema/call, hidden or denied operation, bad arguments, cleanup and task ownership; network auth requires separate host configuration. |
| `agnara-fullstack-starter` | Backend capability with HTTP+MCP and a small frontend consuming HTTP; domain independent of web/agent SDKs | Both adapters invoke the same operation, equivalent contracts/failures, frontend smoke test and explicit combined lifecycle ownership. |

Each repository needs `README.md`, a short application-scoped `AGENTS.md`,
`pyproject.toml`, lockfile, runnable source, tests and CI. Use a clean layout:

```text
src/<project>/
  bootstrap.py
  apps/<context>/
    domain/
    application/
    adapters/inbound/
    adapters/outbound/
tests/
```

An exceptionally small starter may use the documented minimal CLI architecture
instead. Frontend code is separate from domain/application. README installation
and run/test commands must execute unchanged from a fresh checkout. AGENTS.md
links official llms/learning material, requires public imports/version checks,
and names project-specific policy/lifecycle owners; it does not copy this
framework repository's issue-claim or maintainer governance requirements.

Include one completed operation rather than TODO pseudocode. Configure secrets
through explicit environment examples with no credentials. Record which identity
mapping is a fixture and which boundary a deployment must implement. A2A/events/
durable tasks must not appear as available starter profiles. Capture why each
starter exists and test synchronization with canonical examples so a future
release update does not silently teach stale syntax.

Create repositories only under a separately scoped maintainer task with an
owner, license, release/update policy and CI. Prioritize the backend starter
after observing implementation failures in the [benchmark](AGENT_DISCOVERY_BENCHMARK.md).
