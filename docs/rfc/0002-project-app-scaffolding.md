# RFC 0002 — Projects, Apps and Scaffolding

- Status: Draft
- Target: v0.1 developer experience

## Summary

Agnara projects contain multiple protocol-neutral apps.

The CLI can generate project/app structures and add protocol exposures without making those protocols part of the app's identity.

## Motivation

Django demonstrated the value of:

```text
project
  └── multiple apps
```

Agnara retains that mental model for modularity but replaces web-specific app conventions with capability-centric, hexagonal boundaries.

## Definitions

### Project

Composition root and deployable system.

### App

Bounded context that owns capabilities.

### Exposure

Adapter projection of one or more capabilities to a transport.

## Canonical commands

```bash
agnara project create commerce
agnara app create payments
agnara app create payments --with http,mcp
agnara app expose payments a2a
agnara capability create payments refund
```

## Profiles

Profiles are aliases for initial scaffolding.

They cannot change runtime app semantics.

## Default architecture

`modular-hexagonal`.

Reason:

- modularity similar to Django apps;
- domain/application isolation;
- adapters remain replaceable;
- protocol dependencies remain at the edges;
- scales from monolith to independently deployable modules.

## Registry

Apps should be explicitly discoverable through project metadata and/or typed Python composition.

Pure filesystem scanning is insufficient as the only source of truth.

## Generated files

Generators must be deterministic and non-destructive.

No generator may overwrite a user-modified file without explicit permission.

## Multi-app dependency rules

An app may depend on another app only through documented public application contracts/capabilities.

Direct import of another app's adapter/infrastructure layer is an architecture violation.

## Protocol combinations

The same app may expose:

```text
HTTP + MCP
MCP + A2A
HTTP + Events + Tasks
HTTP + MCP + A2A + Events + Tasks
```

without duplicating the domain/application implementation.

## Rejected alternative: `app-mcp` as a runtime type

Rejected because it couples business modularity to a transport.

Accepted only as a CLI shortcut that delegates to:

```text
app create --profile mcp
```

## Rejected alternative: global layer folders

Rejected as the default:

```text
controllers/
services/
repositories/
```

because large projects accumulate unrelated domains in shared layers.

## Open questions

1. exact app descriptor API;
2. manifest vs typed composition source-of-truth balance;
3. whether app-local tests are default;
4. architecture upgrade/migration tooling;
5. plugin-provided scaffolding trust model.
