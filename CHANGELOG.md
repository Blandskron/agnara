# Changelog

Changes to the current 1.x line are summarized here. Published versions and
full history are available through Git tags and GitHub Releases.

## [Unreleased]

### Fixed

- Correct `agnara doctor` exposure messages: A2A reports missing diagnostic
  coverage, Events reports a reserved namespace and Tasks reports an absent
  runtime. Preserve failing checks, exit codes, report format and read-only
  behavior regardless of installed adapter metadata.

- Synchronize active A2A guidance with the unreleased provisional surface,
  completed guide/artifact/host evidence and optional application-owned
  disconnect recipe. Preserve the published 1.0.3 boundary and experimental
  status; clarify CLI diagnostic and threat-model coverage limits.

- Close the standalone quickstart's shared DI container and the telemetry
  example's owned SDK provider on success, errors and cancellation. Preserve
  API-only mode when the optional SDK is absent; surface unrelated import faults.

- Run the HTTP service tutorial's startup, requests and shutdown on one event
  loop; close its singleton provider and join lifespan on errors and cancellation.

### Added

- Add a copyable application-owned A2A disconnect recipe following the reviewed
  ADR 0100 host option. Verify its exact source against installed candidate
  wheels and real sockets, including body limits, refusal ordering, cancellation
  races and shutdown. Existing adapter defaults and public APIs remain unchanged;
  the recipe does not promote protocol support or stability.

- Add real-loopback A2A conformance against a development-only Uvicorn 0.52.4
  fixture: official-client calls, refusals before effects, deadline recovery,
  peer disconnect and graceful shutdown. Clarify that this host does not cancel
  an active handler on socket close; its kernel deadline still owns cleanup.

- Add an executable provisional A2A guide with the official in-process client,
  host-verified identity, denial before effects and owned resource cleanup.
  Validate the exact example against installed candidate wheels in the existing
  cross-platform test gate; network/disconnect support remains unclaimed.

- Publish compiled complete-result output schemas in HTTP OpenAPI 200 JSON
  responses for opted-in operations. Keep `Any` unconstrained, HEAD/204
  bodyless and SSE excluded; reject invalid published schema metadata and
  detach documents from schema-port data.

- Add a provisional `agnara_a2a` surface for the ADR 0098 A2A profile:
  `A2a`, `A2aSkillExposure`, `A2aAgentCard`, `A2aDefinitionError`,
  `build_a2a_app` and the protocol/SDK identity constants (ADR 0099). One
  capability per surface over JSON-RPC at revision 1.0 with a required
  principal resolver; no tasks or streaming. `agnara-a2a` now depends on
  `a2a-sdk[http-server]==1.3.0`. Provisional names may change in a minor
  release. The guide, installed-wheel and bounded host evidence above do not
  establish broader A2A support or promote these names to stable.

- Add read-only `agnara doctor` diagnostics with text/versioned JSON reports
  and failing-check exit codes. Check manifest, app paths, executing Python and
  synchronized declared HTTP/MCP package metadata without importing project or
  adapter code; list runtime checks that remain unimplemented explicitly.

### Changed

- Exercise the ADR 0098 A2A profile in an isolated experiment fixture that
  invokes compiled Agnara plans through the official SDK client. Amend ADR 0098
  to the observed SDK behavior: capability failures use `-32602`/`-32603`, with
  the category in `ErrorInfo.metadata.agnaraCode`; no non-A2A exception may
  escape; nesting ceilings are 47 input and 31 output levels; and only the
  admitted `A2A-Version` header enters SDK state. Retain the hash-locked SDK
  feasibility experiment and immutable protocol/SDK research references.
  This evidence underpins the provisional API above; broader protocol support
  remains unclaimed.

- Refresh immutable GitHub Actions pins for Python setup, CodeQL, uv, artifact
  upload/download and Docker login in the existing CI and publication workflows.

- Reconcile active architecture and package guidance with implemented contracts:
  stable HTTP composition, output validation, public Explorer, actual DI scopes
  and telemetry benchmark evidence. Record verification boundaries and remaining
  gaps for all seven packages; A2A has a provisional surface and Events remains
  a reserved namespace.

### Security

- Move the locked OpenTelemetry API and SDK from 1.44.0 to 1.45.1
  (GHSA-xcq7-p3pf-p88h, unbounded `tracestate` parsing); semantic conventions
  follow to 0.66b1. The development pin is `opentelemetry-sdk==1.45.1`;
  `agnara-telemetry` still publishes `opentelemetry-api>=1.44,<2`.

- Propagate the accepted main-branch security dependency updates into the
  development lock: PyJWT 2.15.0, certifi 2026.10.19 (GHSA-6q48-6c7w-9gw2)
  and multidict 6.9.1 (GHSA-54p9-h82j-f925). Certifi and multidict belong to
  the contributor development/test graph, not published runtime requirements.
- Retain the MCP SDK 2.2.0 fix for GHSA-84m7-p3x7-pcfv (CVE-2026-59951)
  with bounded session-admission, refusal and cleanup regressions from main.
  Add trust-root and items-view reference cleanup regressions for the updated
  contributor dependencies. Protocol revision and first-party versions remain
  unchanged; published 1.0.3 artifacts are unaffected.

### Fixed

- Preserve coroutine and generator provider kinds for callable instances wrapped
  in `functools.partial`, so DI awaits values and owns resource cleanup while
  retaining bound arguments, dependency injection and scope validation.

- Exclude annotated bound-method receivers from dependency compilation and
  introspection, preventing duplicate receiver injection, unbound-receiver
  errors and false singleton scope edges. Keep actual dependencies and ordinary,
  static or unbound parameters governed by their real signatures.

- Resolve annotations through `functools.partial` wrappers using the wrapped
  callable's module and the partial's remaining signature. Preserve typed inputs,
  explicit DI/context injection, keyword defaults and resource cleanup without
  introducing dependencies for positionally bound arguments.

- Classify callable dependency-provider instances by their `__call__`
  implementation, so async providers are awaited and generator providers own
  resource acquisition and teardown. Preserve the registered instance, existing
  function/partial classification and class-constructor behavior.

- Exclude Git-confirmed ignored local recovery files under `.worktrees/recovery/`
  from architecture source scans, avoiding false encoding failures on serialized
  Git status. Continue checking tracked/unignored files and other directories;
  retain the full scan when Git cannot establish the exclusion.

- Validate the unchanged direct streaming tutorial against installed candidate
  wheels, including typed stream units/counts, refusals, redacted interruptions,
  demand and cleanup order, and propagated caller cancellation. Negative proofs
  reject altered observations and leaked tasks; runtime and public API are unchanged.

- Validate each actual stream unit without applying complete-result envelope
  rules. A yielded `Success` or `Failure` cannot bypass an explicit unit schema;
  preserve redacted interruptions, partial-output counts and resource cleanup,
  while unconstrained units retain their original values and identity.

- Read callable handler instances' annotations from their bound `__call__`
  method consistently during plan compilation, dependency resolution and
  introspection. Preserve payload validation, context injection, generator
  cleanup and explicit streaming declarations for these registered handlers.

- Validate handler calling conventions for injected dependencies, execution
  contexts and capability invokers at plan construction. Refuse positional-only
  and variadic parameters before invocation, matching the existing payload
  parameter contract; retain named and keyword-only injection.

- Reject provider parameters with missing annotations or unsupported calling
  conventions during DI graph compilation, before resource acquisition.
  Name the provider and parameter in the startup diagnostic; preserve bound
  named dependencies, keyword-only parameters and lazy provider construction.

- Sample the process-local idempotency store's clock inside each atomic
  transition, so lock contention cannot backdate lease/result retention or
  reuse a timestamp from before expiry. Preserve targeted cleanup and capacity
  bounds with deterministic contention and deadline regressions.

- Report the actual documentation MCP startup refusal category to the operator
  and distinguish redacted I/O failures, while preserving client error contracts.

- Clarify that a dependency fix merged into `develop` resolves a default-branch
  Dependabot alert only after it reaches `main` through release or hotfix review.

- Record how a Dependabot security alert is triaged against the branch model:
  such a pull request always arrives on the default branch, so it is replaced by
  a `security/<issue>-<slug>` branch to `develop` and closed as superseded.
  `.github/dependabot.yml` no longer claims Dependabot lacks a uv ecosystem.

- Drive the mounted Agnara HTTP child's lifespan in the installed-wheel
  side-by-side FastAPI fixture, with same-loop singleton cleanup evidence on
  normal and exceptional host exit and cancellation/failure regression tests.

- Construct installed-wheel FastAPI and Starlette fixtures' runtime on the host
  lifespan loop, with resource cleanup checks on normal and exceptional exits.

- Keep SQLite persistence fixtures' runtime construction, invocation and
  shutdown on one owning event loop, with ordered resource/session cleanup
  evidence for cancellation and exceptional host exits.

- Keep the Litestar interoperability fixture's runtime construction, invocation
  and resource shutdown on the host lifespan's event loop, with cleanup checks
  for handler failures and exceptional test-client exits.

- Accept equivalent JSON numbers for numeric Literal inputs across HTTP and
  MCP while preserving exact direct Python validation and boolean separation.
- Align JSON enum inputs with their published values: separate booleans from
  numbers and prevent `_missing_` hooks from accepting undeclared wire values.
- Classify out-of-range JSON integer-to-float inputs as validation failures
  instead of internal errors; preserve nested field paths and integer union
  alternatives across HTTP and MCP.

### Added

- Runnable direct Python streaming guide covering pull-based demand, early
  abandonment, refusal before effects, partial failure, unit validation and
  cancellation cleanup through the governed public API.

- Validate the exact direct-idempotency guide against isolated candidate wheels,
  including receipt/execution identity reuse, principal isolation, policy denial,
  input conflicts and effect counts, with negative proofs of the consumer gate.

- Validate the unchanged nested-invocation guide against isolated candidate
  wheels, including independent parent/child scope checks, explicit fallback,
  root execution identities and exact handler effects. Add negative proofs
  for altered outcomes, diagnostics, identities, traces and leaked tasks.

- Validate exact runnable guides against isolated candidate wheels: host
  embeddings and SQLite persistence, MCP, HTTP SSE, schemas, dependency lifecycle,
  telemetry, deadlines/cancellation, confirmation and filtered introspection.
  Check observable outcomes, refusal/redaction, identity, detached publications
  and owned teardown with negative regression proofs; keep evidence boundaries
  in the interoperability coverage table.

- Runnable Django async-view guide with explicit application-owned lifecycle,
  host identity/outcome mapping and request-factory cleanup evidence.

- Runnable Litestar embedding guide with native host authentication, explicit
  canonical outcome mapping and same-loop resource cleanup evidence.

- Runnable Starlette embedding guide with explicit host authentication, native
  routes, canonical input/outcome mapping and owned resource cleanup evidence.

- Runnable SQLAlchemy/SQLite persistence guide with an application ledger port,
  explicit host commit/rollback over canonical outcomes, cancellation and
  ordered runtime/session/engine cleanup tests.

- Runnable FastAPI embedding guide with host-owned identity and response
  mapping, policy denial before handler work, concurrent context isolation
  and same-loop runtime cleanup evidence.

- Local read-only documentation MCP tooling with five bounded tools, pinned
  snapshot hashes, deterministic lexical search and official-client stdio tests.
  Setup selects an explicit documentation commit; no hosted endpoint is added.

- Agent discovery and selection guides, versioned documentation index and
  deterministic full reading corpus, public HTTP+MCP example, compact workflows
  and reproducible benchmark design; distinguish published 1.0.3 from unreleased
  fixes and reserved protocol namespaces in documentation and source metadata.

- Community Code of Conduct, Accessibility Statement and a dedicated barrier
  reporting form, with public evidence and private contact options.

- Runnable schema contracts guide showing strict Python input, explicit JSON
  conversion, nested validation and declared output enforcement.

- Runnable dependency injection guide showing explicit bindings, singleton
  and invocation reuse, diamond resolution and owned resource teardown.

- Runnable invocation telemetry guide showing event pairing, correlation
  identity, lifecycle outcomes and observer fault isolation.

- Runnable direct invocation guide demonstrating monotonic deadlines, caller
  cancellation, scope denial and owned task/dependency cleanup.

- Runnable introspection guide showing compiled exposure discovery, per-viewer
  publication before serialization and independent invocation authorization.

- Runnable MCP tool guide using the official in-process client for discovery,
  invocation, scope denial, redacted errors and owned dependency cleanup.

- Runnable confirmation guide showing verifier-backed evidence, exact binding,
  expiry, single-use consumption and authorization before effects.

- Runnable HTTP SSE guide demonstrating terminal outcomes, anonymous scope
  denial, redacted failures and owned producer/dependency cleanup.

- Runnable nested capability invocation guide demonstrating independent parent
  and child authorization through the governed public API.
- Runnable direct idempotency guide covering success reuse, request conflicts
  and policy re-evaluation through the governed public API.

### Changed

- Refresh immutable CI/release action pins for CodeQL 4.39.0, setup-uv 10.3.0,
  upload-artifact 7.0.2 and download-artifact 8.0.2.

- Prune superseded API sketches, duplicate target-architecture prose and
  completed-task chronology. Route readers to current contracts and runnable
  guides, and keep documentation maintenance explicit for contributors.

- Update CodeQL, uv setup and Docker build actions to verified release pins;
  route routine Dependabot action updates through `develop`.
- Edge publication checks accept immutable Docker action updates while retaining
  the required action identity, full commit pin and publication safeguards.
- Release readiness reports the verified published 1.0.3 baseline and refuses
  to treat it as a new publication candidate.

## [1.0.3] - 2026-09-25

### Changed

- Establish the current documentation baseline and remove superseded
  prerelease, migration and publication-recovery material.
- Align all seven synchronized distribution versions, kernel pins and
  package maturity metadata with stable 1.x.
- Correct the PyPI-facing package descriptions and current architecture,
  interoperability, security, operations and agent guidance.
- Add documentation consistency checks to prevent obsolete release language
  and broken internal links from returning.

Runtime behavior, public API, execution semantics and protocol support are
unchanged.

[Unreleased]: https://github.com/Blandskron/agnara/compare/v1.0.3...develop
[1.0.3]: https://github.com/Blandskron/agnara/compare/v1.0.2...v1.0.3
