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

Apps depend on explicit contracts, not each other's internal implementation.

For a modular app, the only public cross-app Python module is:

```text
<project>.apps.<app>.application.contracts
```

It contains transport-neutral types and Protocols that the app offers. Domain
modules, capability handlers, required ports, adapters, `module.py` and tests
remain internal. `application.ports` is not the public surface: its ports name
what that app needs from elsewhere.

Cross-app communication options, in order of preference:

1. capability invocation through an explicit application port;
2. domain/application interface;
3. event publication;
4. shared kernel package for genuinely shared primitives.

Direct imports from one app's infrastructure internals into another app are forbidden.

The first option describes the intended semantic boundary, not a direct
Python call to another handler. Agnara does not yet define internal capability
invocation: a direct call would bypass the target's policy, dependencies,
deadline, telemetry and canonical failures. Initiative I8 owns that future
decision. Until then, project composition may satisfy a public Protocol
through dependency injection without pretending it invoked a capability.

A minimal app has no application layer and publishes no cross-app contract by
default. Needing one is a reason to move to the modular architecture rather
than invent a second public path. See ADR 0066.

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

Project compilation freezes both the project's aggregate capability registry
and every app registry mounted on it. A mounted app may still be shared with
another project, but its declarations are immutable after the first project
compiles; apps not mounted on that project remain open. The freeze is
idempotent, so later compilation of another project using the same app is
valid. Mounting itself does not close registration: declarations added to a
mounted app before compilation are synchronized into the compiled project.

## App descriptor

This section previously sketched a `Module` / `ModuleBuilder` API. Neither
ever existed. The design was settled differently by ADR 0065 and shipped as
`App`, so the sketch is replaced here rather than left for a reader to follow
into names the framework does not have.

An app declares; a project mounts:

```python
from agnara import Agnara, App
from agnara.core.di import DIRegistry

payments = App(
    "payments",
    description="Payment capabilities.",
    module="shop.apps.payments",
)


@payments.capability(description="Refund a captured payment.", idempotent=False)
def refund(payment_id: str) -> str: ...


def register(app: Agnara, dependencies: DIRegistry) -> None:
    app.include(payments)
```

The app name becomes the capability namespace, so the id is
`payments.refund`. The project name does not appear in it: a project is
renamed far more readily than a bounded context, and an id is referenced by
policy rules, audit records and agent manifests.

`AppDescriptor` is the frozen identity behind `App`, and is what introspection
projects. Declaration is separate from mounting, so an app can be imported and
tested without a project.

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
