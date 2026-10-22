# Changelog

Changes to the current 1.x line are summarized here. Published versions and
full history are available through Git tags and GitHub Releases.

## [Unreleased]

### Security

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

- Validate the exact direct-idempotency guide against isolated candidate wheels,
  including receipt/execution identity reuse, principal isolation, policy denial,
  input conflicts and effect counts, with negative proofs of the consumer gate.

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
