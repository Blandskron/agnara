# Changelog

Notable changes to Agnara are recorded here. The format is inspired by Keep a
Changelog, and release versions follow the synchronized PEP 440 policy in ADR
0021.

`0.1.0a2` is the first published release. `0.1.0a1` was tagged but never
reached PyPI: its release run failed in artifact validation, so the publish job
never executed. Every first-party package in the workspace carries the
synchronized version, but only the `agnara` core distribution is uploaded to
PyPI; the adapter packages are versioned and buildable from the repository
without being published. See the `0.1.0a2` scope note below.

## [Unreleased]

### Added

- Added `agnara graph`, which draws capability, dependency and provider
  relationships from the same filtered snapshot `agnara inspect` reads. Every
  introspection command now obtains its data from one shared view, so no
  command has a second discovery path ([#194]).
- Added the `agnara` command and `agnara inspect`, which imports a compiled
  application named as `module:attribute` and presents its filtered
  introspection snapshot as text or deterministic JSON. Both modes build one
  snapshot and apply one visibility decision, chosen on the command line
  ([#192]).
- Added discovery visibility and redaction: `filter_snapshot` decides which
  capabilities a principal may discover and which fields are published, as two
  separate decisions with no default publication set, and marks its result so
  an unfiltered snapshot cannot be served by mistake ([#190]).
- Added the protocol-neutral introspection snapshot in `agnara.introspection`:
  frozen descriptors for apps, capabilities, inputs, dependencies, providers,
  policies and adapter-contributed exposures, built from a compiled
  application, with a versioned JSON data form and no path from a snapshot to
  a runtime object ([#188]).
- Added a comparative MCP tool-invocation benchmark against the pinned SDK's
  `MCPServer`, measuring the handler and official-client boundaries separately
  and reporting synchronous and asynchronous tools apart, with the baseline
  recorded in `docs/benchmarks/mcp-tool-invocation.md` ([#186]).
- Added the MCP tool invocation dispatcher: `McpToolInvoker` and
  `build_mcp_server` serve `tools/call` over the same frozen discovery
  snapshot, enforcing each capability's declared scopes with core's
  `ScopePolicy` before any effect, projecting canonical outcomes as tool
  results, refusing task-augmented and resumed calls as protocol errors, and
  propagating cancellation instead of answering it ([#185]).
- Added `project_mcp_result` for detached JSON success content, canonical tool
  errors without internal details and existing interaction-required projection,
  with explicit rejection of unsupported output values ([#183]).
- Added bounded MCP SDK conformance coverage for discovery, malformed
  pagination, unsupported calls and concurrent request identity/cache isolation,
  with an explicit coverage matrix and exclusions ([#181]).

## [0.1.0a2] - 2026-09-04

First release actually published to PyPI. Same source surface as the tagged
`0.1.0a1`; this version exists because the `0.1.0a1` release run never reached
the publish job and a tag is never moved or reused.

Published to PyPI: `agnara` only. `agnara-http`, `agnara-mcp`, `agnara-cli`,
`agnara-a2a`, `agnara-events` and `agnara-telemetry` share the version but are
not uploaded, so the HTTP, OpenAPI, MCP and CLI surfaces are reachable from a
repository checkout rather than from `pip install agnara`.

### Fixed

- Made the release pipeline's out-of-workspace smoke test deterministic. It
  drove `uv venv` without an interpreter request, so the runner's CPython 3.12
  was selected and the `requires-python >= 3.14` wheel could not be installed,
  failing `Validate built artifacts` before anything could be published. The
  step now creates the environment with an explicit `--python 3.14`, installs
  and runs through that environment's interpreter instead of `uv run`, requires
  exactly one wheel in `dist/`, and asserts the interpreter version, the
  version reported by the installed distribution and that `agnara` resolved
  from `site-packages` rather than from the checkout. The post-publish
  verification step was made deterministic the same way, since a failure there
  would prevent the GitHub Release from being created.

## [0.1.0a1] - 2026-09-04

First public alpha: an architectural proof that Agnara installs and runs as a
real Python distribution. The public API is unstable and this release is not
production-ready.

Tagged but never published. The release run for `v0.1.0a1` failed in
`Validate built artifacts`, so no distribution was uploaded to PyPI and the
GitHub Release was never created. Everything recorded below shipped to PyPI
under `0.1.0a2` instead.

### Added

- Defined the MCP Task and multi-round-trip boundary: MRTR as the only
  resumption mechanism on the pinned revision, the Tasks extension neither
  implemented nor advertised, explicit request-state boundary installation
  on the lowlevel server tier, and confirmation evidence kept separate from
  client-echoed round state (ADR 0042).
- Added deterministic projection of canonical interaction-required
  confirmation outcomes to official MCP `InputRequiredResult` form
  elicitations, with strict canonical-detail validation, minimal safe
  serialization and explicit separation from evidence verification and MRTR
  resumption ([#172]).
- Added a request-scoped MCP authorization bridge from official SDK verified
  identity context to protocol-neutral principals, with credential-free
  explicit identity mapping, fail-closed redacted errors, isolated static
  scope filtering, and private immediately stale discovery results ([#170]).
- Added an official SDK MCP discovery boundary for frozen projected tools,
  including pinned `server/discover` capability advertisement, deterministic
  detached `tools/list` results, conservative private cache hints, and explicit
  invalid-cursor handling ([#168]).
- Added projection from compiled capability inputs to official MCP SDK `Tool`
  definitions, with closed object schemas, protected-parameter exclusion,
  deterministic required fields, detached JSON-safe schema data, and ignored
  isolated pytest basetemp directories used by repository verification
  ([#166]).
- Added deterministic MCP tool exposure registration through
  `Mcp(app).tool(capability)`, including explicit wire-name overrides,
  startup collision checks, capability ownership validation, and immutable
  compiled snapshots ([#164]).
- Pinned the first MCP adapter baseline to specification `2026-07-28` and the
  official Python SDK `2.1.1`, with an adapter-owned version contract,
  dependency-boundary tests and explicit deferral of unfinished protocol and
  conformance surfaces ([#162]).
- Added a reproducible in-process ASGI benchmark comparing Agnara HTTP with a
  direct reference, Starlette 1.6.0, FastAPI 0.141.1 and Litestar 2.24.0 using
  deterministic rotating samples, correctness checks, raw/environment/version
  evidence and no CI timing threshold; ADR 0041 retains the dependency-free
  direct ASGI boundary ([#159]).
- Enforced the documentation asset policy with immutable exact-version remote
  resource metadata, SHA-384 SRI and anonymous-CORS validation, exact HTML/CSP
  correspondence, canonical deployment origin allowlists, and repository-wide
  vendored hash/license/packaging checks; pinned local assets and no UI remain
  zero-network baselines ([#157]).
- Added a required Playwright 1.62.0/Chromium documentation-browser gate for
  Swagger UI, ReDoc and Scalar covering emitted CSP/security headers, XSS and
  undeclared-network blocking, mobile/keyboard smoke behavior, credential
  storage, disabled routes, OAuth redirect boundaries and per-UI try-it; no
  unconditional documentation default is selected ([#155]).
- Added pinned Scalar API Reference 1.67.0 local and opt-in CDN providers with
  verified licensed assets and SRI, explicit telemetry/plugin/agent/font
  boundaries, independently disabled try-it and documented partial OpenAPI
  3.2/accessibility support; the documentation default remains deferred until
  shared browser evidence exists ([#153]).
- Added pinned ReDoc CE 2.5.3 local and opt-in CDN documentation providers,
  including verified licensed assets, SRI, untrusted-spec sanitization and an
  explicit blob-worker CSP requirement; ReDoc truthfully refuses canonical
  OpenAPI 3.2 and try-it instead of silently degrading either ([#151]).
- Added pinned Swagger UI 5.32.14 documentation providers: the production
  baseline serves verified licensed assets locally, while a separate
  exact-version CDN provider requires explicit remote-asset permission and
  uses SRI; online validation, credential persistence and try-it are disabled
  by default, and known OpenAPI 3.2 gaps are declared ([#149]).
- Added an immutable HTTP publication plan where schema serving, each
  documentation UI, Explorer and per-UI try-it are selected independently;
  UIs without a schema endpoint receive document bytes instead of an
  unserved URL ([#147]).
- Added compiled HTTP surface routes for already-produced schema,
  documentation and Explorer artifacts: paths are explicit and static,
  compilation order is deterministic, collisions reserve the whole path
  against capability routes, and unmatched requests delegate unchanged to
  capability dispatch ([#145]).
- Added the replaceable documentation-provider contract: a provider receives
  an already-filtered OpenAPI document and never the compiled registry, must
  name the OpenAPI versions it was tested against and the features it does not
  support, becomes unavailable with a diagnostic rather than rendering a
  version it does not support, and needs both its own declaration and
  deployment permission before requiring an external origin ([#141]).
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
- Added dependency-free deterministic OpenAPI 3.2 projection from explicitly
  publishable compiled HTTP exposures, reusing compiled input schemas and
  filtering hidden operations before document assembly ([#135]).
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

- Pinned CPython 3.14 in every `release.yml` job and made a wrong
  interpreter fail loudly. The artifact-validation job built its clean-room
  environment on whatever Python the runner offered, so the first tagged run
  could not install its own `>=3.14` wheel, and the publish job's
  post-release check carried the same defect where it would have failed
  after upload.

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

[Unreleased]: https://github.com/Blandskron/agnara/compare/v0.1.0a2...develop
[0.1.0a2]: https://github.com/Blandskron/agnara/compare/v0.1.0a1...v0.1.0a2
[0.1.0a1]: https://github.com/Blandskron/agnara/releases/tag/v0.1.0a1
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
[#141]: https://github.com/Blandskron/agnara/issues/141
[#145]: https://github.com/Blandskron/agnara/issues/145
[#147]: https://github.com/Blandskron/agnara/issues/147
[#149]: https://github.com/Blandskron/agnara/issues/149
[#151]: https://github.com/Blandskron/agnara/issues/151
[#153]: https://github.com/Blandskron/agnara/issues/153
[#155]: https://github.com/Blandskron/agnara/issues/155
[#157]: https://github.com/Blandskron/agnara/issues/157
[#159]: https://github.com/Blandskron/agnara/issues/159
[#162]: https://github.com/Blandskron/agnara/issues/162
[#164]: https://github.com/Blandskron/agnara/issues/164
[#166]: https://github.com/Blandskron/agnara/issues/166
[#168]: https://github.com/Blandskron/agnara/issues/168
[#170]: https://github.com/Blandskron/agnara/issues/170
[#172]: https://github.com/Blandskron/agnara/issues/172
[#123]: https://github.com/Blandskron/agnara/issues/123
[#125]: https://github.com/Blandskron/agnara/issues/125
[#133]: https://github.com/Blandskron/agnara/issues/133
[#135]: https://github.com/Blandskron/agnara/issues/135
[#181]: https://github.com/Blandskron/agnara/issues/181
[#183]: https://github.com/Blandskron/agnara/issues/183
[#185]: https://github.com/Blandskron/agnara/issues/185
[#186]: https://github.com/Blandskron/agnara/issues/186
[#188]: https://github.com/Blandskron/agnara/issues/188
[#190]: https://github.com/Blandskron/agnara/issues/190
[#192]: https://github.com/Blandskron/agnara/issues/192
[#194]: https://github.com/Blandskron/agnara/issues/194
