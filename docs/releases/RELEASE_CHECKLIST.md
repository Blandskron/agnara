# Agnara 1.0.3 release checklist

This release synchronizes documentation and metadata with the current stable
1.x framework. Runtime behavior, public API, execution semantics and protocol
support are unchanged. No feature, optimization or Python 3.15 implementation
belongs in this release.

- [x] Root and seven package READMEs describe current behavior and limits.
- [x] Historical migration, candidate and recovery documentation is removed
  after current knowledge is moved to canonical guides.
- [x] ROADMAP, BACKLOG, maturity, interoperability, security, threat model and
  agent guidance agree with the source and tests.
- [x] Internal Markdown links and runnable examples pass.
- [x] Seven distributions use version 1.0.3, Python >=3.14, Apache-2.0,
  consistent stable classifiers and exact `agnara==1.0.3` adapter pins.
- [x] `docs/public-api.json` and runtime semantics are unchanged from the
  `develop` starting commit.
- [ ] Full CI, architecture, public API, browser, protocol, security, benchmark,
  link and anti-drift gates pass on the accepted commit.
- [x] Seven wheels and seven sdists build and validate locally from this tree.
- [x] All wheels install together in a clean Python 3.14 environment without
  first-party index resolution; public imports and CLI smoke pass.
- [x] Built `agnara` wheel metadata and long description show the stable
  1.x contract, current installation and Python floor.
- [ ] Maintainer reviews the release description and publication evidence.
- [ ] Protected publication uses all three phases on one accepted `main` SHA;
  PyPI, tag, GitHub Release and reference container are verified afterward.

Checkmarks are evidence-dependent. The status JSON does not turn unexecuted
checks into passes.

Local pytest (3656 passed, 36 skipped), browser tests (32 passed), version,
lockfile, lint, format, typing, artifact and clean-install checks passed.
The local measured performance gate exceeded three ratios on an idle Windows
rerun. Its numeric budgets were not changed; CI and maintainer review remain
required before the release can be considered ready.
