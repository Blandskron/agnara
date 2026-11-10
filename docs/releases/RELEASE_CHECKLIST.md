# Agnara 1.0.3 release record

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
- [x] Full CI, architecture, public API, browser, protocol, security, benchmark,
  link and anti-drift gates passed on the accepted commit; see the three release
  runs below.
- [x] Seven wheels and seven sdists build and validate locally from this tree.
- [x] All wheels install together in a clean Python 3.14 environment without
  first-party index resolution; public imports and CLI smoke pass.
- [x] Built `agnara` wheel metadata and long description show the stable
  1.x contract, current installation and Python floor.
- [ ] A formal review by Blandskron is not recorded on PR #514. GitHub records
  an approval by `blandskron-AI` and a merge by Blandskron. The historical
  review gap remains visible; publication cannot create a missing review.
- [x] Protected publication used all three phases on
  `c25d9eb5b2d432f652c4661a1925cb38baa63c82`; the final run verified the
  seven distributions, created the immutable tag and GitHub Release, and
  published the reference images.

Checkmarks are evidence-dependent. The status JSON does not turn unexecuted
checks into passes.

Local pytest (3656 passed, 36 skipped), browser tests (32 passed), version,
lockfile, lint, format, typing, artifact and clean-install checks passed.
The local measured performance gate exceeded three ratios on an idle Windows
rerun. Its numeric budgets were unchanged; the required release CI passed on
the accepted commit. This local result remains part of the preparation record.

Publication evidence: [bootstrap-1](https://github.com/Blandskron/agnara/actions/runs/36198149576),
[bootstrap-2](https://github.com/Blandskron/agnara/actions/runs/36198710966),
[final](https://github.com/Blandskron/agnara/actions/runs/36199330668), and
[v1.0.3](https://github.com/Blandskron/agnara/releases/tag/v1.0.3).
New publication is paused until approximately March 2027; this record does
not select another target.
