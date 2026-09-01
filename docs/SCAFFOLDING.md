# Scaffolding Architecture

## Objective

Generated apps should be immediately understandable, testable and extensible.

Scaffolding must optimize for:

- separation of concerns;
- low coupling;
- discoverability;
- portability;
- agent readability;
- incremental complexity.

It must NOT generate dozens of meaningless empty files.

## Default: modular hexagonal app

Example:

```text
src/commerce/apps/payments/
├── __init__.py
├── module.py
├── domain/
│   ├── __init__.py
│   ├── models.py
│   ├── value_objects.py
│   └── errors.py
├── application/
│   ├── __init__.py
│   ├── capabilities.py
│   └── ports.py
├── adapters/
│   ├── __init__.py
│   ├── inbound/
│   │   └── __init__.py
│   └── outbound/
│       └── __init__.py
└── tests/
    ├── __init__.py
    └── test_capabilities.py
```

If created with:

```bash
agnara app create payments --with http,mcp
```

then only the requested inbound adapters are added:

```text
adapters/
└── inbound/
    ├── http.py
    └── mcp.py
```

No MCP import appears outside the MCP adapter file/package.

No HTTP request type appears in application/domain code.

## Responsibility of each layer

### `domain/`

Pure business concepts.

Allowed:

- entities;
- value objects;
- domain errors;
- pure domain services;
- invariants.

Avoid framework imports.

### `application/`

Use cases/capabilities and ports required by those use cases.

Allowed:

- capability handlers;
- commands/queries when useful;
- application services;
- input/output contracts;
- dependency port protocols.

The application layer may use small Agnara core authoring types when required, but should not know transports.

### `adapters/inbound/`

Protocol projections into application capabilities.

Examples:

- HTTP routes;
- MCP tools/resources/prompts;
- A2A skills;
- event consumers;
- CLI commands.

Inbound adapters map protocol-specific data to capability invocation.

### `adapters/outbound/`

Implement application ports.

Examples:

- PostgreSQL repository;
- Redis cache;
- external REST client;
- message publisher;
- S3 storage.

An app may have no outbound adapters.

### `module.py`

Composition/registration boundary for the app.

It should register:

- app metadata;
- capabilities;
- exposures;
- providers;
- policies.

It should remain small.

### `tests/`

App-local tests may be colocated for portability.

Project-wide conformance and integration tests remain under root `tests/`.

## Minimal architecture

```text
apps/health/
├── __init__.py
├── module.py
├── capabilities.py
└── tests/
    └── test_capabilities.py
```

A minimal app can later be upgraded:

```bash
agnara app refactor health --architecture modular-hexagonal
```

This command is future work and must never perform destructive refactors without a migration plan.

## Why modular hexagonal

Classic layered architecture across an entire repository often creates global folders:

```text
controllers/
services/
repositories/
models/
```

As systems grow, unrelated domains become coupled through those shared layers.

Agnara instead prefers:

```text
apps/
    payments/
        domain/
        application/
        adapters/
    catalog/
        domain/
        application/
        adapters/
```

This keeps high cohesion inside the business module and clear boundaries around it.

## Vertical slices

Within a large app, a later evolution may organize application capabilities by feature:

```text
application/
    create_payment/
    refund_payment/
    get_payment/
```

Agnara should allow this without changing runtime semantics.

Directory layout is a developer architecture choice, not a runtime capability type.

## Generated code policy

Templates should contain:

- executable examples;
- minimal comments explaining extension points;
- no fake production implementations;
- no database choice unless requested;
- no cloud/provider choice unless requested;
- no empty `service.py` just because a template expects one.

## Architecture metadata

The generator should record enough metadata for tooling to know:

```text
app name
architecture template
installed exposures
path
```

Metadata must not duplicate runtime truth unnecessarily.

## Agent readability

Every generated app should be understandable from:

```bash
agnara inspect <app> --json
```

and from the filesystem alone.

Hidden registry magic is discouraged.
