# Agnara 1.0.1 release checklist

This release publishes the synchronized security patch set after v1.0.0.
It carries four authorization/transport security fixes and one release-flow
hardening fix while keeping the documented 1.x public API and runtime contract.

- [x] Changelog contains a dated 1.0.1 section with the five post-baseline
  security/release fixes.
- [x] Release notes document the 1.0.1 scope, upgrade guidance and fix set.
- [x] Seven distributions use version 1.0.1 with exact `agnara==1.0.1`
  adapter pins and a refreshed workspace lockfile.
- [ ] Local quality gates pass on the candidate commit (lint, format, typing,
  targeted tests and release checks).
- [ ] Full CI, architecture, protocol, browser, security and performance lanes
  pass on the accepted main-targeting release PR.
- [ ] Maintainer formally reviews and approves publication evidence.
- [ ] Protected release workflow runs all three phases from one accepted SHA.
- [ ] PyPI projects, immutable tag and GitHub Release are verified, then
  release-only tracking changes propagate back to develop.

Checkmarks are evidence-dependent. The status JSON does not turn unexecuted
checks into passes.
