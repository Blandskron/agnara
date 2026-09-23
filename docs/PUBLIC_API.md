# Public API Stability

This document owns Agnara's Python compatibility policy. The exact, ordered
inventory is [`public-api.json`](public-api.json); the generated
[API reference](API_REFERENCE.md) is a reader-facing projection of that
inventory and does not create a second contract.

## 1.0 decision

The 1.0 contract contains **166 stable exports across 13 modules**: 166
distinct names at 166 canonical import paths. Leaf-module re-export aliases
are no longer in `__all__` and are not supported public API.

`stable` means a name, its canonical import path, signature, and documented
behaviour are compatible throughout the current major line. `provisional` and
`experimental` remain vocabulary for a future deliberate classification, but
neither occurs in the 1.0 inventory. `internal` names are outside the manifest
and have no compatibility promise.

## Canonical modules

| Distribution | Module | Stable exports |
| --- | --- | ---: |
| `agnara` | `agnara` | 41 |
| `agnara` | `agnara.di` | 9 |
| `agnara` | `agnara.execution` | 32 |
| `agnara` | `agnara.exposure` | 7 |
| `agnara` | `agnara.introspection` | 23 |
| `agnara` | `agnara.policy` | 1 |
| `agnara` | `agnara.schema` | 13 |
| `agnara-a2a` | `agnara_a2a` | 0 |
| `agnara-cli` | `agnara_cli` | 4 |
| `agnara-events` | `agnara_events` | 0 |
| `agnara-http` | `agnara_http` | 14 |
| `agnara-mcp` | `agnara_mcp` | 20 |
| `agnara-telemetry` | `agnara_telemetry` | 2 |

Reserved `agnara_a2a` and `agnara_events` namespaces are deliberately
classified with no exports. All other non-private implementation modules are
internal unless their name is re-exported from this table's module through the
manifest.

## Required migrations

```python
# Dependency injection
from agnara.di import DIRegistry

# Introspection snapshot
for application in snapshot.applications:
    print(application.name)
```

`agnara.core.di` is an implementation namespace; import the nine supported DI
types from `agnara.di`. `IntrospectionSnapshot.apps` and the top-level JSON
field `apps` have been renamed to `applications`. The `apps` member of an
`ApplicationDescriptor` still represents bounded contexts and is unchanged.

`ExecutionContext` narrows two previously unchecked inputs. `principal` must
be a `Principal`; a duck-typed token, claims mapping or session object is now
a `TypeError` at construction. `principal`, `confirmation_evidence` and
`idempotency` are read-only after construction and raise `InvocationError` on
assignment, because a nested child derives its authority from the parent's
principal and a reassignable one is an amplification path. Supply authority
through the constructor from the composition root that authenticated the
caller. `state` and `tracking_id` remain mutable; neither is authority.

Both narrowings land before the 1.0 contract freezes. Under the 1.x rules
below they would each require a major release, so they are deliberately taken
now rather than after the promise exists.

## Enforcement

The architecture tests compare each literal `__all__` to the manifest, ensure
every listed value imports, and require every governed export to be stable.
The installed-artifact gate imports every stable canonical value after wheels
are installed outside the checkout.

```bash
python scripts/check_public_imports.py path/to/application
python scripts/check_distributions.py --workspace . --require-installed
```

The first command also audits imports in Markdown Python examples. Repository
examples and current guides must use only governed paths; ADR and RFC records
may quote historical spellings.

## 1.x compatibility contract

Within 1.x, removing or moving a stable name, changing a signature
incompatibly, narrowing accepted input, changing documented result or failure
semantics, or changing a documented emitted schema incompatibly requires a new
major release. A minor release may add a new name, optional parameter, optional
output field, failure code for a previously unclassified condition, or telemetry
attribute.

A stable name deprecated in `1.n` may not be removed before `2.0`. A
deprecation includes a changelog entry, replacement and migration guidance.
Security repairs may shorten this path only when the changelog records why
without exposing embargoed details.

Adapters retain their own contracts: HTTP status/problem/SSE projections and
MCP result projections must remain compatible inside their major line. A
transport adapter must not weaken an `agnara` core commitment. Schema contracts
cover documented accepted and required shapes, not incidental `repr`, exception
message wording, dictionary order, or private implementation classes.
