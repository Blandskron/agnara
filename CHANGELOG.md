# Changelog

Notable changes to Agnara are recorded here. The format is inspired by Keep a
Changelog, and release versions follow the synchronized PEP 440 policy in ADR
0021.

All work listed below is unreleased. The repository has no release tag yet;
package version `0.0.0` is a development sentinel, not a published release.

## [Unreleased]

### Added

- Established a dependency-free internal ASGI 3 HTTP boundary that preserves
  raw adapter inputs and rejects unsupported protocols explicitly ([#107]).
- Added a deterministic two-phase HTTP route registry with fail-fast template
  collision detection and immutable compiled trie matching ([#109]).
- Added compiled explicit HTTP path/query/header/JSON-body binding with strict
  wire decoding, scalar conversion, bounded chunked bodies, and shared core
  schema validation ([#113]).
- Added deterministic non-streaming ASGI success responses with compact UTF-8
  JSON, dataclass and enum projection, correct `HEAD`/`204` behavior, and
  fail-before-start validation ([#115]).
- Added RFC 9457 failure responses with an exhaustive, reviewed
  `FailureCode`-to-status table, occurrence-independent problem titles,
  optional compiled problem-type URIs, collision-free nested failure details,
  `internal_failure` redaction, and a prebuilt last-resort internal problem
  response ([#117]).
- Added transport-level RFC 9457 problems for failures that precede a
  capability: classified binding failures, `404`, `405` with a required
  `Allow` header, `413` and `415`, sharing one problem-type namespace with
  capability failures ([#129]).
- Added compiled HTTP exposures and the end-to-end request path: startup
  validation and an immutable route-to-plan registry, then match, bind,
  invoke and serialize, with `HEAD` served from `GET`, `root_path` stripping,
  no response on a client disconnect, and a query-free problem `instance`
  ([#131]).
- Added structured execution telemetry hooks (E4.8).
- Defined Policy, PolicyResult interface and added policies tuple to CapabilityDefinition.
- Defined Principal and AnonymousPrincipal for policy evaluation.
- Added immutable granted scopes to principals and a transport-neutral
  `ScopePolicy` for deterministic all-required-scope evaluation ([#90]).
- Defined the protocol-neutral confirmation boundary: verified evidence,
  interaction-required outcomes, replay binding, and pre-handler enforcement
  sequencing ([#94]).
- Implemented verifier-backed confirmation policies, immutable interaction
  requests, explicit evidence on execution contexts, and pre-handler canonical
  outcome mapping ([#96]).
- Defined protocol-neutral delegation semantics with explicit actor/subject
  separation, monotonic authority attenuation, bounded verified chains and
  confirmation binding ([#101]).
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
- Compiled protocol-neutral capability input schemas with deterministic
  required/unknown-input failures and validated values on the invocation path
  ([#111]).
- Transport-neutral direct invocation of compiled plans with explicit context
  injection, DI ownership, sync/async handlers and deterministic resource
  cleanup ([#65]).
- Optional monotonic invocation deadlines covering dependency resolution and
  handler execution, with timeout cleanup and remaining-time introspection
  ([#69]).
- Immutable protocol-neutral `Success`, `Failure`, and `FailureCode` outcomes,
  plus an `invoke_result` boundary that preserves direct-call ergonomics,
  redacts unexpected exceptions, and propagates cancellation ([#71]).

### Changed

- Contributors on the maintainer Windows workstation can now run the complete
  five-command quality gate locally. The `E0.13` record no longer claims that
  Ruff and `ty` are unrunnable there; CI stays the authoritative
  cross-platform record ([#120]).
- Direct invocation explicitly propagates task cancellation while cleaning up
  resources entered before cancellation, including during dependency
  construction ([#67]).
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

- HTTP dispatch now strips `root_path` only at a complete mount-path segment,
  preventing a mount such as `/api` from capturing a textual prefix such as
  `/apiary` ([#133]).
- Every `CHANGELOG.md` reference link resolves again. Nine had lost or never
  received a definition and rendered as literal text; governance tests now
  reject an undefined reference, an unreferenced definition, a duplicate, and
  a definition whose URL does not match its own number ([#125]).
- Restored the em-dashes, arrows and box-drawing characters that a lossy
  cp1252 write had replaced with literal question marks across `README.md`,
  `BACKLOG.md`, `CONTRIBUTING.md`, one core module docstring and four test
  modules. Every diagram in the README is readable again, and a
  repository-integrity test now fails on reintroduction ([#123]).
- The multi-agent coordination CLI no longer aborts with `UnicodeEncodeError`
  on a narrow console codec. Output framing is ASCII, and GitHub-sourced
  titles, worker names and scopes degrade to replacement characters instead of
  killing the command ([#119]).
- Removed unresolved merge markers from the changelog and added a governance
  regression check that prevents their reintroduction ([#87]).
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
[#38]: https://github.com/Blandskron/agnara/issues/38
[#62]: https://github.com/Blandskron/agnara/issues/62
[#65]: https://github.com/Blandskron/agnara/issues/65
[#67]: https://github.com/Blandskron/agnara/issues/67
[#69]: https://github.com/Blandskron/agnara/issues/69
[#71]: https://github.com/Blandskron/agnara/issues/71
[#87]: https://github.com/Blandskron/agnara/issues/87
[#90]: https://github.com/Blandskron/agnara/issues/90
[#94]: https://github.com/Blandskron/agnara/issues/94
[#96]: https://github.com/Blandskron/agnara/issues/96
[#101]: https://github.com/Blandskron/agnara/issues/101
[#107]: https://github.com/Blandskron/agnara/issues/107
[#109]: https://github.com/Blandskron/agnara/issues/109
[#111]: https://github.com/Blandskron/agnara/issues/111
[#113]: https://github.com/Blandskron/agnara/issues/113
[#115]: https://github.com/Blandskron/agnara/issues/115
[#117]: https://github.com/Blandskron/agnara/issues/117
[#119]: https://github.com/Blandskron/agnara/issues/119
[#120]: https://github.com/Blandskron/agnara/issues/120
[#129]: https://github.com/Blandskron/agnara/issues/129
[#131]: https://github.com/Blandskron/agnara/issues/131
[#123]: https://github.com/Blandskron/agnara/issues/123
[#125]: https://github.com/Blandskron/agnara/issues/125
[#133]: https://github.com/Blandskron/agnara/issues/133
