# ADR 0065 — An App Owns Its Capability Namespace

- Status: Proposed
- Date: 2026-09-06
- Tracking: GitHub Issue #254 (E1A.1, E1A.2)

## Context

ADR 0011 decided that an Agnara app is a bounded context. `ARCHITECTURE.md`
section 13 places App between Project and Capabilities. RFC 0002 left the
mechanism open, as the first of its open questions:

> 1. exact app descriptor API;

Until now there was no runtime for any of it. Every generated app registered
into the project's single `Agnara`, so its capabilities took the **project**
name as their namespace. The consequence was not theoretical:

```
agnara project create shop
agnara app create payments
agnara app create catalog
```
```
DuplicateCapabilityError: capability shop.get_record is already registered
```

Both templates give every app the same domain-neutral `get_record` and
`list_records`, so the scaffolder's own output did not compose with itself.

The model had already anticipated the answer. `CapabilityId`'s docstring:

> `namespace` is a single identifier naming **the owning app** or application
> namespace, such as `payments`.

Only the runtime was missing.

## Decision

### An app is a declaration surface with an identity

`AppDescriptor` is the identity: a `name`, an optional `description`, an
optional `module`. Frozen and hashable, so a project can talk about its apps
rather than only about their capabilities.

`App` is the declaration surface: a descriptor, its own registry, and the same
`capability` decorator `Agnara` offers.

```python
payments = App("payments", description="Money movement.", module="shop.apps.payments")

@payments.capability(description="Read one record.", idempotent=True)
def get_record(reference: str) -> dict[str, str]: ...
```

### The app name is the capability namespace

`payments.get_record`, not `shop.payments.get_record` and not
`shop.get_record`. `CapabilityId` is two segments and its namespace is the
owning app, so this changes no shape — it supplies the value that shape always
expected.

**The project name does not appear in a capability id.** An id is referenced
by policy rules, audit records and agent manifests, and a project is renamed
far more readily than a bounded context is. Putting the project in the id
would make renaming a directory a breaking change to a published contract.

### Declaration is separate from mounting

An app declares at import time; a project mounts with `Agnara.include(app)`.

Importing an app is therefore enough to inspect or unit-test it, with no
project and no composition root. And a project states what it contains in one
place instead of having that emerge from import side effects.

`include` is registration, so the ADR 0005 freeze applies: including after
`compile()` raises, exactly as declaring after `compile()` does.

### `Agnara` gains one method and no responsibilities

`ARCHITECTURE.md` section 5 warns that the application object must not become
a god object, and `agnara/application.py` says so in its own first paragraph.
So the declaration surface lives on `App`; `Agnara.include` only merges a
registry it is handed.

The shared decorator behaviour moved to a private `agnara._declaration`, used
by both. The typed signature is repeated on each surface because overloads
cannot be usefully inherited, but the behaviour is not, so a capability cannot
come to mean something slightly different depending on where it was declared.

### `App` has no `compile`

Freezing is a project-wide decision. An app that could freeze itself would let
one module close a registry another module was still writing to.

## Consequences

- Two apps from the same scaffold compose. The defect above is closed, and
  `test_two_apps_may_declare_the_same_name` is the regression.
- Generated capability ids change from `<project>.<name>` to
  `<app>.<name>`. Nothing published depends on the old form: `0.1.0a3`
  publishes only the core, whose `Agnara.capability` is untouched, and app
  scaffolding arrived after it.
- Two apps that share a *name* still collide, and should: that is a duplicated
  identity rather than an accidental clash. E1A.3 will report it as such
  instead of as a capability error.
- `AppDescriptor.module` gives E1A.4 somewhere to point a reader at the
  source, and matches what `agnara.toml` already records.

## Alternatives considered

**Three-segment ids, `<project>.<app>.<name>`.** Rejected: `CapabilityId` is
deliberately a namespace and a name, splitting on the *first* separator so a
dotted qualified name stays unambiguous. A third segment would either break
that rule or make the project part of every published id.

**A view from the application, `agnara.bounded_context(descriptor)`.**
Rejected: it puts the declaration surface back on `Agnara` and gives an app no
existence of its own, so an app could not be imported and tested without a
project.

**Keep one registry and disambiguate on collision.** Rejected: it treats a
bounded context as an accident to be worked around rather than as the unit
ADR 0011 says it is, and any disambiguation would produce ids nobody declared.
