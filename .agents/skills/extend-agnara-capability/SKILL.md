---
name: extend-agnara-capability
description: Add schemas, dependency providers, policy checks, tests or telemetry to an existing Agnara capability while preserving public imports and lifecycle.
---

# Extend an existing capability

Inspect the installed version and current definition, compiled plans and host
ownership. Read only the relevant canonical source:

| Change | Guide / example |
| --- | --- |
| Inputs and explicit outputs | [schema guide](../../../docs/SCHEMA_CONTRACTS.md); use [HTTP dataclasses](../../../examples/http_service.py) for published 1.0.3, avoiding unreleased enum/numeric fixes |
| Dependency injection | [DI guide](../../../docs/DEPENDENCIES.md), [resource example](../../../examples/dependencies.py) |
| Scopes and confirmation | [policy section](../../../docs/AGENT_GUIDE.md#policies-and-authorization), [confirmation](../../../examples/confirmation.py) |
| Telemetry | [guide](../../../docs/TELEMETRY.md), [hooks example](../../../examples/invocation_telemetry.py) |
| Adapter tests | [same-capability test](../../../tests/docs/test_http_mcp_example.py) |

Use [canonical exports](../../../docs/public-api.json). Bind provider types
before compilation. Declare `output=...` when output validation is needed.
Preserve trusted principals, policy-before-effects order, cancellation and
resource teardown on the owning loop. Caller data must not replace DI values,
choose execution identity or stand in for verified confirmation evidence.

Test the changed behavior through `invoke_result` or the real adapter boundary,
including a refusal path and cleanup. Telemetry observers must not affect the
business result or expose payload/secrets. Do not add an LLM SDK or unrelated
dependency for these changes. When touching this framework, follow its
[AGENTS.md](../../../AGENTS.md) workflow; application repositories keep their
own contributor rules.
