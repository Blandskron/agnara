# Runnable examples for coding agents

Choose the smallest relevant source, then read its associated tests. These
programs use governed public imports. Python >=3.14 is required. In the
repository, run `uv sync` then `uv run python examples/<file>.py`.

| Task | Canonical source | Validation / deeper guide |
| --- | --- | --- |
| Minimal capability and direct invocation | [minimal_capability.py](minimal_capability.py) | [test](../tests/docs/test_minimal_capability_example.py), [agent path](../docs/AGENT_GUIDE.md) |
| Capability metadata, DI and policy | [quickstart.py](quickstart.py) | [core guide](../packages/agnara/README.md) |
| HTTP backend and dataclass JSON contract | [http_service.py](http_service.py) | [composition guide](../docs/HTTP_COMPOSITION.md), [public surface tests](../tests/architecture/test_public_http_surface.py) |
| Official-client MCP service | [mcp_tools.py](mcp_tools.py) | [test](../tests/docs/test_mcp_tools_example.py), [guide](../docs/MCP_TOOLS.md) |
| Same capability invoked over HTTP + MCP | [http_mcp.py](http_mcp.py) | [test](../tests/docs/test_http_mcp_example.py) |
| Schemas/contracts | [schema_contracts.py](schema_contracts.py) | [test](../tests/docs/test_schema_contracts_example.py), [guide](../docs/SCHEMA_CONTRACTS.md); enum/numeric edge cases target unreleased fixes |
| Dependency providers and teardown | [dependencies.py](dependencies.py) | [test](../tests/docs/test_dependencies_example.py), [guide](../docs/DEPENDENCIES.md) |
| Verifier-backed confirmation policy | [confirmation.py](confirmation.py) | [test](../tests/docs/test_confirmation_example.py), [guide](../docs/CONFIRMATION.md) |
| Execution telemetry without exporter | [invocation_telemetry.py](invocation_telemetry.py) | [test](../tests/docs/test_telemetry_example.py), [guide](../docs/TELEMETRY.md) |
| Optional OpenTelemetry bridge | [telemetry.py](telemetry.py) | [integration evidence](../tests/integration/telemetry/test_opentelemetry_shared_host.py) |
| Filtered discovery | [introspection.py](introspection.py) | [test](../tests/docs/test_introspection_example.py), [guide](../docs/INTROSPECTION.md) |
| Streaming and cancellation | [http_sse.py](http_sse.py), [deadlines.py](deadlines.py) | [SSE guide](../docs/HTTP_SSE.md), [deadline guide](../docs/DEADLINES.md) |
| Explicit direct idempotency / nested invocation | [direct_idempotency.py](direct_idempotency.py), [nested_invocation.py](nested_invocation.py) | [idempotency](../docs/DIRECT_IDEMPOTENCY.md), [composition](../docs/NESTED_INVOCATION.md) |

The minimal and HTTP+MCP programs run with installed PyPI **1.0.3** packages.
Most guides were added after publication but teach existing public contracts;
new schema bug-fix behavior is qualified above and in its guide. Use
[Git release history](https://github.com/Blandskron/agnara/releases/tag/v1.0.3)
for an immutable baseline, not the package version of an editable checkout.
Demo principals and in-process clients do not implement production authentication.

For external use install matching first-party versions and required optional
dependencies; `uv run` in this workspace uses editable development packages.
Assert observable results, denials and cleanup. Never count a successful import
or an HTTP status alone as proof that the intended capability ran correctly.
