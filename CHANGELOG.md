# Changelog

Changes to the current 1.x line are summarized here. Published versions and
full history are available through Git tags and GitHub Releases.

## [Unreleased]

## [1.0.1] - 2026-10-15

### Security

- Redact missing scope labels from caller-facing authorization denials in
  direct, HTTP and MCP calls while retaining opt-in operator diagnostics.
- Match incoming publication methods case-sensitively so lowercase or
  malformed methods cannot reach GET-only schema, documentation, discovery or
  Explorer content.
- Require whole-response private or no-store cache directives for
  viewer-specific Explorer and discovery output, preventing shared caches from
  replaying filtered metadata across viewers.
- Reject directly constructed execution plans that omit declared scope,
  application or confirmation policies, preventing direct and MCP calls from
  bypassing capability authorization.

### Fixed

- Pin every phased release dispatch to the successful first-phase candidate
  commit and compare published PyPI SHA-256 values against the retained build
  artifact set before publication can continue.

[Unreleased]: https://github.com/Blandskron/agnara/compare/v1.0.1...develop
[1.0.1]: https://github.com/Blandskron/agnara/compare/v1.0.0...v1.0.1
