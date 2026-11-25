# Requests for Comment

## Open and partially answered

| RFC | Remaining work |
| --- | --- |
| [0005 · Delegation](0005-protocol-neutral-delegation.md) | Authority model and policy integration. |
| [0008 · Framework embedding](0008-framework-embedding-and-ecosystem-composition.md) | Composition beyond the host boundary resolved by [ADR 0094](../adr/0094-framework-neutral-embedding-contract.md). |
| [0009 · Streaming](0009-streaming-model.md) | Additional projections beyond the [kernel contract](../adr/0084-core-streaming-contract.md) and [HTTP SSE](../adr/0085-http-sse-streaming-projection.md). |
| [0010 · A2A](0010-a2a-initial-projection.md) | Profiles beyond the [provisional complete-result surface](../adr/0099-a2a-provisional-public-surface.md). |
| [0011 · Events](0011-event-initial-projection.md) | Implemented as provisional inbound profile under accepted [ADR 0101](../adr/0101-initial-inbound-event-projection.md) and proposed [ADR 0103](../adr/0103-events-provisional-public-surface.md); outbound publishing, batching and stability promotion remain open. |
| [0012 · Durable execution](0012-durable-execution-boundary.md) | Boundary settled by accepted [ADR 0102](../adr/0102-durable-execution-ownership.md); future task/workflow runtime projections remain separate work. |
| [0013 · WebSocket streaming](0013-websocket-streaming-projection.md) | Feasibility and boundary questions for projecting ADR 0084 capability streams over ASGI WebSockets. |

## Answered proposals

These links resolve the historical citations in ADRs. Use the current
contracts for application and contributor guidance.

| Proposal in Git history | Current contract |
| --- | --- |
| [0001 · Capability runtime](https://github.com/Blandskron/agnara/blob/5aab12ac352a59b7d20925f1af90b80159d3277f/docs/rfc/0001-capability-runtime.md) | [Architecture](../../ARCHITECTURE.md) and [API design](../API_DESIGN.md) |
| [0002 · Scaffolding](https://github.com/Blandskron/agnara/blob/5aab12ac352a59b7d20925f1af90b80159d3277f/docs/rfc/0002-project-app-scaffolding.md) | [Scaffolding](../SCAFFOLDING.md) and [manifest](../PROJECT_MANIFEST.md) |
| [0003 · HTTP documentation](https://github.com/Blandskron/agnara/blob/5aab12ac352a59b7d20925f1af90b80159d3277f/docs/rfc/0003-http-documentation-and-capability-explorer.md) | [HTTP composition](../HTTP_COMPOSITION.md) and [ADR 0018](../adr/0018-replaceable-documentation-providers.md) |
| [0004 · Dependency injection](https://github.com/Blandskron/agnara/blob/5aab12ac352a59b7d20925f1af90b80159d3277f/docs/rfc/0004-dependency-injection.md) | [Dependency guide](../DEPENDENCIES.md) |
| [0006 · Exposure model](https://github.com/Blandskron/agnara/blob/5aab12ac352a59b7d20925f1af90b80159d3277f/docs/rfc/0006-unified-exposure-model.md) | [ADR 0070](../adr/0070-unified-exposure-model.md) and [ADR 0071](../adr/0071-public-http-composition-api.md) |
| [0007 · Distribution versions](https://github.com/Blandskron/agnara/blob/5aab12ac352a59b7d20925f1af90b80159d3277f/docs/rfc/0007-distribution-version-identity.md) | [ADR 0095](../adr/0095-synchronized-releases-and-curated-changelog.md) |
