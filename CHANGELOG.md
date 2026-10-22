# Changelog

Changes to the current 1.x line are summarized here. Published versions and
full history are available through Git tags and GitHub Releases.

## [Unreleased]

### Security

- Update the official MCP SDK dependency from 2.1.1 to 2.2.0 for
  GHSA-84m7-p3x7-pcfv (CVE-2026-59951), removing the vulnerable exact pin
  for consumers using stateful Streamable HTTP. The MCP protocol revision
  remains `2026-07-28`; first-party versions and published artifacts are unchanged.

### Fixed

- Reconcile the main-branch 1.0.3 release record with its existing published
  tag so the unchanged release-workflow guard can validate the historical baseline.

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
