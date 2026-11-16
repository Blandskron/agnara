# External standards and research

Current framework behavior is specified in the linked contracts and tested in
the repository. The earlier investigations, including individual browser
measurements and ecosystem snapshots, are preserved in
[Git history](https://github.com/Blandskron/agnara/blob/fd21a83956579740e7cc9de25c7d2a16b77f5757/docs/REFERENCE_RESEARCH.md).

## OpenAPI and documentation providers

Agnara projects the compiled HTTP exposures to OpenAPI. Documentation
providers consume that projection. [ADR 0018](adr/0018-replaceable-documentation-providers.md)
records the provider boundary. [HTTP composition](HTTP_COMPOSITION.md) owns
the supported OpenAPI versions, provider behavior and asset configuration.
[Quality gates](../QUALITY_GATES.md) defines browser conformance.

- [OpenAPI Specification](https://spec.openapis.org/oas/)
- [Swagger UI](https://github.com/swagger-api/swagger-ui)
- [ReDoc](https://github.com/Redocly/redoc)
- [Scalar](https://github.com/scalar/scalar)
- [Subresource Integrity](https://www.w3.org/TR/SRI/)
- [Content Security Policy Level 3](https://www.w3.org/TR/CSP3/)

## Protocols and telemetry

| Subject | Primary sources | Agnara contract or research |
| --- | --- | --- |
| MCP | [Model Context Protocol](https://modelcontextprotocol.io/specification) and [Python SDK](https://github.com/modelcontextprotocol/python-sdk) | [Pinned conformance profile](MCP_CONFORMANCE.md) |
| A2A | [Specification repository](https://github.com/a2aproject/A2A) and [Python SDK](https://github.com/a2aproject/a2a-python) | [Provisional surface](adr/0099-a2a-provisional-public-surface.md) and [feasibility evidence](research/a2a-initial-feasibility.md) |
| AsyncAPI and events | [AsyncAPI specification](https://github.com/asyncapi/spec) and [CloudEvents specification](https://github.com/cloudevents/spec) | [Event projection research](rfc/0011-event-initial-projection.md) |
| OpenTelemetry | [Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/) and [Metrics API](https://opentelemetry.io/docs/specs/otel/metrics/api/) | [Telemetry guide](TELEMETRY.md) |

## llms.txt

The [llms.txt proposal](https://llmstxt.org/) describes a Markdown discovery
index. [ADR 0053](adr/0053-llms-txt-documentation-index.md) records why the
public documentation index is independent of runtime capability discovery.
[Agent discovery](AGENT_DISCOVERY.md) records the sources and generation
commands in this checkout.

## Python and tooling

The [Python 3.14 release notes](https://docs.python.org/3/whatsnew/3.14.html)
describe the language baseline. [Quality gates](../QUALITY_GATES.md) owns
the supported validation commands using [uv](https://docs.astral.sh/uv/),
[Ruff](https://docs.astral.sh/ruff/) and [ty](https://docs.astral.sh/ty/).
The [application model](APPLICATION_MODEL.md) records how Agnara uses
[Django-style project and app ergonomics](https://docs.djangoproject.com/en/6.0/intro/tutorial01/)
for capability composition.
