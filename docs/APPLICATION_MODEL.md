# Application and Module Model

## Purpose

Agnara adopts one of Django's most useful usability ideas — a project can contain multiple independently understandable applications — but adapts it to a capability-first, protocol-neutral architecture.

In Agnara, an **App** is a bounded business module.

It is NOT an HTTP app, MCP app, A2A app, worker, or event consumer by identity.

Those are **exposures** of the app's capabilities.

## Core hierarchy

```text
Workspace / Project
    │
    ├── App: users
    │      ├── domain
    │      ├── application
    │      ├── capabilities
    │      └── exposures
    │            ├── HTTP
    │            └── MCP
    │
    ├── App: payments
    │      ├── domain
    │      ├── application
    │      ├── capabilities
    │      └── exposures
    │            ├── HTTP
    │            ├── MCP
    │            └── Tasks
    │
    └── App: recommendations
           ├── domain
           ├── application
           ├── capabilities
           └── exposures
                 ├── MCP
                 └── A2A
```

## Terminology

### Project

A deployable/composable Agnara system.

A project owns:

- global configuration;
- app registry;
- runtime composition;
- installed protocol adapters;
- shared infrastructure bindings;
- observability configuration;
- deployment entrypoints.

### App

A cohesive business or technical bounded context.

Examples:

```text
users
catalog
payments
billing
search
recommendations
audit
notifications
```

Bad app identities:

```text
api
mcp
http
database
controllers
services
```

because they describe technical layers or protocols instead of capabilities.

### Capability

An executable business operation owned by an app.

Examples:

```text
payments.create_payment
payments.refund_payment
catalog.get_product
users.disable_account
```

### Exposure

A protocol-specific way to invoke a capability.

Examples:

```text
HTTP POST /payments
MCP tool create_payment
A2A skill create_payment
event consumer payment.requested
task create_payment
CLI command payment create
```

## Multi-app projects

A project can host any number of apps:

```text
commerce/
    users/
    catalog/
    orders/
    payments/
    recommendations/
```

Apps should depend on contracts, not reach through each other's internal implementation.

Cross-app communication options, in order of preference:

1. capability invocation through an explicit application port;
2. domain/application interface;
3. event publication;
4. shared kernel package for genuinely shared primitives.

Direct imports from one app's infrastructure internals into another app are forbidden.

## App portability

An app should be movable between Agnara projects when its external ports can be satisfied.

This does not require every app to be independently publishable, but the architecture should preserve that possibility.

## App lifecycle

Conceptually:

```text
DISCOVER
→ REGISTER APP
→ REGISTER CAPABILITIES
→ REGISTER EXPOSURES
→ COMPILE PROJECT GRAPH
→ FREEZE
→ START
```

Apps must not mutate the global registry after freeze.

## App descriptor

Each app exposes a small descriptor or registration function.

Illustrative API:

```python
from agnara import Module

module = Module(
    name="payments",
    description="Payment capabilities",
)
```

or:

```python
def install(module: ModuleBuilder) -> None:
    ...
```

The exact API remains subject to the RFC and golden examples.

## Important invariant

A CLI profile may choose initial exposures, but it must never change the semantic identity of the app.

Therefore:

```text
agnara app create payments --profile api
```

means:

```text
create app "payments"
+
scaffold HTTP exposure
```

It does NOT mean:

```text
create a special HTTP-only application type
```

This distinction is foundational.
