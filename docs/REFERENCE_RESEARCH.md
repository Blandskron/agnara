# Reference Research Baseline

Last reviewed: 2026-08-31.

This document records external standards and projects that influence Agnara. It is not a dependency list.

## Python 3.14

Agnara intentionally starts at Python 3.14.

Relevant direction:

- free-threaded CPython is officially supported as an optional build;
- modern asyncio/structured-concurrency tools are available;
- the project should avoid GIL-dependent correctness.

Reference:

- https://docs.python.org/3.14/whatsnew/3.14.html
- https://docs.python.org/3/howto/free-threading-python.html

## FastAPI

Study FastAPI for:

- developer API ergonomics;
- type-driven design;
- OpenAPI integration;
- dependency patterns;
- ecosystem lessons;
- backward-compatibility cost.

Do not copy its HTTP-first architecture.

Reference:

- https://github.com/fastapi/fastapi
- https://fastapi.tiangolo.com/history-design-future/

## OpenAPI

Target modern OpenAPI support through the HTTP adapter.

Current baseline investigated:

- OpenAPI 3.2.0.

Reference:

- https://spec.openapis.org/oas/latest.html

## MCP

MCP is a primary protocol adapter target.

The 2026-07-28 specification introduced/strengthened concepts including:

- stateless protocol core;
- Multi Round-Trip Requests;
- header-based routing;
- cacheable lists;
- authorization changes;
- extension framework;
- Tasks as an extension.

Reference:

- https://blog.modelcontextprotocol.io/posts/2026-07-28/

The MCP adapter must pin and test the exact supported specification/SDK version rather than assuming evergreen compatibility.

## A2A

A2A is a post-v0.1 adapter target.

Current reviewed line:

- A2A Protocol 1.0.

The protocol supports independent agent interoperability, discovery, tasks, streaming and multiple protocol bindings.

Reference:

- https://github.com/a2aproject/A2A/blob/main/docs/specification.md

## AsyncAPI

Event-driven support should project to AsyncAPI rather than inventing a documentation format.

Current reviewed line:

- AsyncAPI 3.1.0.

Reference:

- https://www.asyncapi.com/docs/reference/specification/v3.1.0

## uv

Recommended workspace/package manager because its workspace model maps well to Agnara's package boundaries.

Reference:

- https://docs.astral.sh/uv/concepts/projects/workspaces/

## Ruff

Recommended lint and formatting tool.

Reference:

- https://docs.astral.sh/ruff/

## ty

Recommended initial type checker for a Python 3.14-native project. Keep the type-checking strategy replaceable if ecosystem requirements change.

Reference:

- https://docs.astral.sh/ty/

## Research rule

External projects are sources of lessons, not templates to copy wholesale.

Every imported architectural idea must be evaluated against Agnara's capability-first thesis.

## Django project/app ergonomics

Agnara deliberately learns from Django's project/application separation and `startapp` generator.

Useful lessons:

- one project can contain multiple apps;
- an app has a conventional package structure;
- scaffolding removes mechanical setup;
- explicit app registration/introspection improves modularity.

Agnara changes the semantics:

- apps are capability bounded contexts, not web-app packages;
- transports are adapters;
- generated default architecture is modular hexagonal;
- machine-readable and agent-oriented CLI output is required.

References:

- https://docs.djangoproject.com/en/6.0/intro/tutorial01/
- https://docs.djangoproject.com/en/6.0/ref/django-admin/#startapp
- https://docs.djangoproject.com/en/6.0/ref/applications/
