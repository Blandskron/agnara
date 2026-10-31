# Runnable examples for coding agents

Choose the smallest relevant source, then read its associated tests. These
programs use governed public imports. Python >=3.14 is required. In the
repository, run `uv sync` then `uv run python examples/<file>.py`.

| Task | Canonical source | Validation / deeper guide |
| --- | --- | --- |
| Minimal capability and direct invocation | [minimal_capability.py](minimal_capability.py) | [test](../tests/docs/test_minimal_capability_example.py), [agent path](../docs/AGENT_GUIDE.md) |
| Capability metadata, DI and policy | [quickstart.py](quickstart.py) | [lifecycle tests](../tests/docs/test_standalone_example_lifecycle.py), [core guide](../packages/agnara/README.md) |
| HTTP backend, dataclass JSON contract and owned ASGI lifespan | [http_service.py](http_service.py) | [lifecycle test](../tests/docs/test_http_service_example.py), [composition guide](../docs/HTTP_COMPOSITION.md), [public surface tests](../tests/architecture/test_public_http_surface.py) |
| Official-client MCP service | [mcp_tools.py](mcp_tools.py) | [test](../tests/docs/test_mcp_tools_example.py), [guide](../docs/MCP_TOOLS.md) |
| Provisional A2A service through the official in-process client | [a2a_service.py](a2a_service.py) | [test](../tests/docs/test_a2a_service_example.py), [guide](../docs/A2A_SERVICE.md); unreleased checkout/candidate wheels only, no network-support claim |
| Optional application-owned A2A disconnect helper | [a2a_disconnect.py](a2a_disconnect.py), injected into [a2a_service.py](a2a_service.py) | [ownership tests](../tests/a2a/test_a2a_disconnect_recipe.py), [guide](../docs/A2A_SERVICE.md#try-the-opt-in-recipe); copyable companion module, not an Agnara export or standalone server |
| Same capability invoked over HTTP + MCP | [http_mcp.py](http_mcp.py) | [test](../tests/docs/test_http_mcp_example.py) |
| Runtime embedded inside native FastAPI routes | [fastapi_embedding.py](fastapi_embedding.py) | [test](../tests/docs/test_fastapi_embedding_example.py), [guide](../docs/FASTAPI_EMBEDDING.md); optional pinned host fixture |
| Runtime embedded inside native Starlette routes | [starlette_embedding.py](starlette_embedding.py) | [test](../tests/docs/test_starlette_embedding_example.py), [guide](../docs/STARLETTE_EMBEDDING.md); optional pinned host fixture |
| Runtime embedded inside native Litestar routes | [litestar_embedding.py](litestar_embedding.py) | [test](../tests/docs/test_litestar_embedding_example.py), [guide](../docs/LITESTAR_EMBEDDING.md); optional pinned host fixture |
| Runtime invoked from native Django async views | [django_embedding.py](django_embedding.py) | [test](../tests/docs/test_django_embedding_example.py), [guide](../docs/DJANGO_EMBEDDING.md); optional request-factory fixture with explicit application-owned lifecycle |
| Application-owned SQLAlchemy/SQLite transactions | [sqlite_persistence.py](sqlite_persistence.py) | [test](../tests/docs/test_sqlite_persistence_example.py), [guide](../docs/SQLITE_PERSISTENCE.md); optional pinned infrastructure fixture |
| Schemas/contracts | [schema_contracts.py](schema_contracts.py) | [test](../tests/docs/test_schema_contracts_example.py), [guide](../docs/SCHEMA_CONTRACTS.md); enum/numeric edge cases target unreleased fixes |
| Dependency providers and teardown | [dependencies.py](dependencies.py) | [test](../tests/docs/test_dependencies_example.py), [guide](../docs/DEPENDENCIES.md) |
| Verifier-backed confirmation policy | [confirmation.py](confirmation.py) | [test](../tests/docs/test_confirmation_example.py), [guide](../docs/CONFIRMATION.md) |
| Execution telemetry without exporter | [invocation_telemetry.py](invocation_telemetry.py) | [test](../tests/docs/test_telemetry_example.py), [guide](../docs/TELEMETRY.md) |
| Optional OpenTelemetry bridge and owned provider shutdown | [telemetry.py](telemetry.py) | [lifecycle tests](../tests/docs/test_standalone_example_lifecycle.py), [integration evidence](../tests/integration/telemetry/test_opentelemetry_shared_host.py) |
| Filtered discovery | [introspection.py](introspection.py) | [test](../tests/docs/test_introspection_example.py), [guide](../docs/INTROSPECTION.md) |
| Direct streaming, demand and early closure | [direct_streaming.py](direct_streaming.py) | [test](../tests/docs/test_direct_streaming_example.py), [guide](../docs/DIRECT_STREAMING.md); current-checkout output fixes |
| HTTP streaming and cancellation | [http_sse.py](http_sse.py), [deadlines.py](deadlines.py) | [SSE guide](../docs/HTTP_SSE.md), [deadline guide](../docs/DEADLINES.md) |
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
