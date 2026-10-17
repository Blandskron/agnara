# Changelog

Changes to the current 1.x line are summarized here. Published versions and
full history are available through Git tags and GitHub Releases.

## [Unreleased]

### Fixed

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

- Run the exact schema-contracts guide against isolated candidate wheels,
  checking typed Python/JSON results, input identity, error paths/redaction and
  compiled schemas with negative validation proofs.

- Run the exact HTTP SSE guide against isolated candidate wheels, independently
  validating wire frames, terminal/problem outcomes, disconnect, empty streams
  and ordered producer/provider cleanup with negative validation proofs.

- Run the exact MCP tools guide against isolated candidate wheels and the
  pinned official client, verifying SDK discovery/results, rejected-call effects
  and connection/provider cleanup with negative validation proofs.

- Run the exact FastAPI and SQLite guide sources against isolated candidate
  wheels, checking HTTP outcomes/correlation and persisted rows, rollback and
  ordered cleanup, with negative validation proofs.

- Run the Starlette, Litestar and Django host-guide examples against isolated
  installed candidate wheels, verifying JSON outcomes, authorized effects and
  ordered cleanup with negative validation proofs.

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

- Refresh immutable CI/release action pins for CodeQL 4.38.3, setup-uv 10.3.0,
  upload-artifact 7.0.2 and download-artifact 8.0.2.

- Distinguish current API contracts from future convenience sketches and align
  architecture guidance with implemented HTTP SSE and provider boundaries.

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
