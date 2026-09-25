# Backlog

This file contains work still open on `develop`. Completed A1–A8 and 1.0.0
construction tasks are preserved in Git history, the accepted ADRs and the
[release evidence](docs/releases/v1.0.0.md); they are not instructions for
current implementation. GitHub Issues are the executable work units.

## Active maintenance

- [~] [#507](https://github.com/Blandskron/agnara/issues/507) — Separate
  current 1.x documentation from future platform research and historical
  evidence. Acceptance: code-backed current claims, one canonical reading
  path, working links and documentation/architecture gates.
- [ ] Review publication bootstrap and candidate selection for the next 1.x
  patch. Acceptance: one immutable candidate commit per version, current
  version selected in every job and a protected publication path. Track in a
  dedicated Issue before implementation.
- [ ] Configure an independent reviewer identity when one is available.

## Python 3.15 readiness

The [program specification](docs/research/python-315-readiness.md) owns
activation, dependencies and acceptance criteria. These items are unstarted;
the published 1.0.0 release alone does not substitute for the explicit
activation record required by that plan. Python >=3.14 remains the supported
baseline.

- [ ] P315-01 — Conventional CPython 3.15 compatibility.
- [ ] P315-02 — Independent CPython 3.15t core and ecosystem validation.
- [ ] P315-03 — Free-threading concurrency audit.
- [ ] P315-04 — Conventional 3.14 vs 3.15 benchmark baseline.
- [ ] P315-05 — Conventional 3.15 vs free-threaded benchmark.
- [ ] P315-06 — JIT experiment.
- [ ] P315-07 — Profiling / Tachyon evidence.
- [ ] P315-08 — Lazy imports research.
- [ ] P315-09 — frozendict research.
- [ ] P315-10 — Sentinel research.
- [ ] P315-11 — Dependency compatibility matrix.
- [ ] P315-12 — Official support declaration after evidence review.

## Future platform work

[ROADMAP.md](ROADMAP.md) describes provisional U1–U10 programs. They are
research/design horizons, not ready implementation items. Add a backlog item
only after an accepted decision gives it a bounded deliverable and testable
acceptance criteria.
