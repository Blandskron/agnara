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

## Implemented form

`agnara project create` is the first generator (E0A.1, ADR 0060). It
establishes the mechanism the rest of EPIC 0A reuses: a generator builds a
plan without touching the filesystem, and an apply step writes it. `--dry-run`
and `--json` render that same plan, so a preview cannot disagree with the
result, and conflicts are detected against the whole plan before the first
write rather than discovered halfway through one.

Two content decisions are deliberate. The generated `bootstrap.py` declares no
example capability — `agnara app create` is where capabilities arrive — but it
does establish the convention every tool reads, so
`agnara inspect <project>.bootstrap:app --path src` works immediately. And
`settings.py` reads no environment: where configuration comes from is a
security-relevant decision a generator must not make silently.

The generated project depends on `agnara` and nothing else.

## Implemented default template

`agnara app create` generates the modular-hexagonal layout above (E0A.3/E0A.4,
ADR 0061). Answering this document's rule that a generator "must NOT generate
dozens of meaningless empty files", the generated app runs: a domain, an
application port, capabilities that depend on that port, an in-memory outbound
adapter that implements it, and tests that pass.

The example is domain-neutral — a `Record` with a `Reference` — because an app
may be called `payments`, `catalog` or `users`, and an invented banking domain
in a catalog is code its first reader deletes. What is not neutral is the
direction of every dependency, which four tests enforce: no generated module
imports a transport, no domain or application module imports an adapter, the
domain imports nothing from the application, and `module.py` is the only
non-test module that knows both the application and its adapters.

`adapters/inbound/` is created as a documented, empty package. Only requested
inbound adapters are added, and `--with` is E0A.6.
