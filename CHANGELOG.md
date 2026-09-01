# Changelog

Notable changes to Agnara are recorded here. The format is inspired by Keep a
Changelog, and release versions follow the synchronized PEP 440 policy in ADR
0021.

All work listed below is unreleased. The repository has no release tag yet;
package version `0.0.0` is a development sentinel, not a published release.

## [Unreleased]

### Added

- Python 3.14 workspace with seven explicit package boundaries and
  cross-platform quality gates.
- Protocol-neutral `CapabilityId` and `CapabilityDefinition` value types with
  effects, risk, confirmation and idempotency metadata.
- Issue/branch/PR/review governance, branch rulesets and evidence-based
  AI-agent attribution.
- Synchronized pre-1.0 package versioning and a curated changelog/release
  workflow ([#16]).
- Capability-first architecture for generated OpenAPI, replaceable HTTP
  documentation providers and protocol-neutral Agnara Explorer introspection.
- `Agnara` composition root and the `@app.capability` decorator, usable bare
  or with metadata. Ids default to `<app>.<function>` with an explicit
  override, descriptions default to the docstring summary, and the
  decorated function is returned unchanged ([#21]).
- `scopes` on `CapabilityDefinition`, declarative permission labels a
  policy engine may require ([#21]).
- Schema port: `SchemaAdapter` and `TypeSchema` protocols, a JSON Schema
  export contract, and `StandardSchemaAdapter`, a strict standard-library
  reference implementation covering primitives ([#27]).
- `SchemaError` and `ValidationError`, the latter carrying a path to the
  offending value so adapters can render it per protocol ([#27]).
- Recursive standard-library schemas for typed lists, string-keyed
  dictionaries, fixed and variadic tuples, unions, literals and enums, with
  strict nested validation and deterministic JSON Schema fragments ([#30]).
- Strict dataclass instance schemas with recursively compiled fields,
  deterministic nested validation paths, default-aware required properties
  and compile-time diagnostics for unsupported directional or recursive
  forms ([#32]).
- An isolated, executable msgspec schema-adapter prototype covering strict
  conversion, JSON Schema generation and protocol-neutral error translation,
  with limitations recorded for the later adapter comparison ([#34]).
- An isolated, executable Pydantic schema-adapter prototype covering strict
  conversion, JSON Schema generation and protocol-neutral error translation,
  with limitations recorded for the later adapter comparison ([#38]).
- `CapabilityRegistry` and `FrozenCapabilityRegistry`: deterministic
  registration order, duplicate-id rejection, a freeze step that yields an
  immutable thread-safe view, lookup by id or dotted string, and
  introspection by namespace and declared effect ([#19]).
- Immutable `ExecutionPlan` startup compilation, which snapshots each
  capability's direct DI requirements after validating the complete provider
  graph ([#62]).
- Transport-neutral direct invocation of compiled plans with explicit context
  injection, DI ownership, sync/async handlers and deterministic resource
  cleanup ([#65]).

### Changed

- Agent-assisted commits now resolve authorized public identities through a
  provider-neutral registry. Materially authored Codex changes use the
  verified `openai-codex[bot]` GitHub identity, while fixed global hooks and
  unverified identities remain forbidden ([#36]).
- `CapabilityDefinition.declare()` carries the authoring-shaped argument
  types, so the documented `effects={...}, risk="high"` calls typecheck
  without suppression while the attributes keep their narrow types ([#24]).

- Core frozen value types retain slots while using one internal construction
  rule for deterministic mutation failures.

### Fixed

- Unknown assignment or deletion on frozen slotted core values now raises
  `FrozenInstanceError` instead of CPython 3.14's confusing internal
  `TypeError` ([#3]).

[Unreleased]: https://github.com/Blandskron/agnara/compare/main...develop
[#3]: https://github.com/Blandskron/agnara/issues/3
[#16]: https://github.com/Blandskron/agnara/issues/16
[#19]: https://github.com/Blandskron/agnara/issues/19
[#21]: https://github.com/Blandskron/agnara/issues/21
[#24]: https://github.com/Blandskron/agnara/issues/24
[#27]: https://github.com/Blandskron/agnara/issues/27
[#30]: https://github.com/Blandskron/agnara/issues/30
[#32]: https://github.com/Blandskron/agnara/issues/32
[#34]: https://github.com/Blandskron/agnara/issues/34
[#36]: https://github.com/Blandskron/agnara/issues/36
[#62]: https://github.com/Blandskron/agnara/issues/62
[#65]: https://github.com/Blandskron/agnara/issues/65
