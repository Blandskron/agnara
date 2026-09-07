# ADR 0066 — Cross-App Dependencies Use Explicit Public Contracts

- Status: Proposed
- Date: 2026-09-06
- Tracking: GitHub Issue #266 (E1A.5)

## Context

ADR 0011 made an app a bounded context, and ADR 0065 gave that context a
runtime identity and capability namespace. `ARCHITECTURE.md` permits one app
to depend on another app's "public application contract" while forbidding an
import of another app's adapter. That is directionally correct but not an
executable rule: no document says which module is public, whether domain types
are shared, or whether importing and directly calling another app's capability
is safe.

The last question is security-sensitive. A direct Python call to another
capability is only a function call. It does not compile or execute the target
capability's policies, dependency graph, deadline, telemetry, confirmation or
canonical failure boundary. Calling it cross-app would make policy bypass look
like ordinary composition. Initiative I8 exists to design internal capability
invocation with explicit context propagation; this decision must not pre-empt
it.

Generated modular apps already have an `application/` layer, but its
`capabilities.py` and `ports.py` serve different purposes. Capabilities are
implementations registered with the runtime. Ports describe services the app
requires from outside. Neither is an explicit surface the app promises to
other bounded contexts.

## Decision

### One module is the cross-app Python surface

A modular app publishes Python types and Protocols for other apps from:

```text
<project>.apps.<app>.application.contracts
```

Only that exact module is a public cross-app import target. Its contents are
ordinary, transport-neutral declarations: value-shaped types, commands,
queries, events, result shapes and Protocols that describe behaviour the app
offers. It may depend on the Python standard library and deliberately public
shared-kernel types. It must not import an adapter, a composition module or a
runtime dependency value.

The module name is intentionally explicit rather than inferred from
`__all__`, a leading underscore or a package re-export. A reader and an
architecture checker can reach the same answer without importing application
code.

### Everything else inside another app is internal

One app must not import another app's:

- `domain/` implementation or value objects;
- `application/capabilities.py`;
- `application/ports.py` (these describe what the target requires, not what it
  offers);
- adapters, including inbound and outbound implementations;
- `module.py` composition boundary;
- tests or test fixtures;
- any other application module not named `contracts.py`.

An app may use all of its own layers according to the existing inward
dependency rule. The project composition root may import app `module.py`
files to mount them; it is not itself an app and is therefore not a cross-app
dependency.

### Importing a contract does not authorize invocation

A contract type can be exchanged without calling another capability. A
Protocol may be satisfied through dependency injection by project composition.
Neither makes a capability invocation.

Cross-app capability calls remain unsupported as a framework operation until
I8 decides nested execution context, principal and delegation propagation,
deadline and cancellation behaviour, policy re-evaluation, transaction
boundaries, recursion and telemetry nesting. Applications must not describe a
direct handler call as an Agnara capability invocation.

### Minimal apps publish no cross-app contract by default

The minimal architecture has no `application/` layer. It therefore publishes
no cross-app Python contract. When a minimal app needs one, that is concrete
evidence it has outgrown the layout; moving to modular-hexagonal names the
boundary rather than adding a second convention.

### Generated projects enforce the rule without importing code

Every generated project includes an AST-based architecture test. It resolves
absolute and relative imports under `src/<project>/apps/`, permits same-app
imports, permits the exact `application.contracts` module across apps, and
reports every other cross-app import as an offender.

The test is static and standard-library-only. It does not execute application
modules, guess from runtime registration or turn the manifest into Python's
semantic source of truth. Existing projects can copy the test; a future
`agnara doctor` may expose equivalent analysis, but this ADR does not add that
command.

## Consequences

- A cross-app boundary is visible from a path and enforceable in CI.
- Generated modular apps gain one meaningful `contracts.py`; their example
  capabilities use its `RecordView`, so it is executable documentation rather
  than an empty placeholder.
- Generated projects gain one architecture test that remains useful as apps
  are added.
- Public contract evolution becomes an application compatibility concern.
  Before 1.0, generated examples may evolve with changelog entries; user apps
  own their own compatibility policy.
- The rule deliberately leaves capability composition unresolved. This is a
  constraint against policy bypass, not a substitute for I8.
- Existing generated projects are not rewritten. Generation remains
  non-destructive.

## Alternatives considered

### Treat every application module as public

Rejected. It exposes implementation handlers and required ports, prevents
refactoring within a bounded context and makes direct policy-bypassing calls
look supported.

### Share domain types directly

Rejected as the default. It couples two bounded contexts at their innermost
layer. A genuinely shared primitive belongs in an explicitly owned shared
kernel, not whichever app happened to define it first.

### Make `application/__init__.py` the public surface

Rejected for now. Re-exports require executing a package to discover its
surface and make a static boundary checker less precise. An exact module path
is smaller and reversible; a later public API decision may add ergonomic
re-exports without changing which declarations are contracts.

### Allow imports of another app's capability and document that calls are unsafe

Rejected. The import exists in order to call or otherwise depend on the
handler. A warning would normalize a security-sensitive bypass before the
runtime has semantics for it.

### Add runtime-enforced internal invocation now

Rejected as out of scope. I8 is `RESEARCH` because propagation and policy
semantics need an RFC. A directory-boundary issue must not settle them by
accident.
