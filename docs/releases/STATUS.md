# Release Status

Generated from `docs/releases/release-status.json` and verified by
`uv run python scripts/check_release_readiness.py`.
Assessed on **2026-09-05** against commit **`f7f53cd`**.

```text
Current target      0.1.0a3  (Integration Alpha)
Overall status      IN_PROGRESS
Readiness           83% of mandatory gates  (10 of 12)
Previous release    0.1.0a2, published 2026-09-04
Next target         0.1.0a4  (Application Alpha)
```

The readiness percentage is **informational only**. A release is ready when
*every* mandatory gate is satisfied, never because a percentage looks high.

---

## Satisfied gates

| Gate | Kind | Evidence |
| --- | --- | --- |
| Full supported test suite passes | evidence | `uv run pytest` — 2003 passed, 31 skipped (browser-only, run in their own CI lane) |
| Package build succeeds | evidence | `uv build --package agnara` — wheel and sdist produced |
| Clean-environment installation smoke test succeeds | evidence | wheel installed into a fresh 3.14.4 venv; `agnara` imports from `site-packages`, not the checkout |
| Python 3.14 baseline verified | automated | all seven packages declare `requires-python >= 3.14`; CI asserts the interpreter |
| HTTP integration tests pass | evidence | 691 HTTP + 25 cross-surface integration tests; 31 real-browser cases in the required CI lane |
| MCP integration and conformance tests pass | evidence | 157 tests against pinned `mcp==2.1.1`, including `tests/mcp/test_sdk_conformance.py` |
| CLI smoke tests pass | evidence | 200 CLI tests; `agnara --version` and `--help` verified |
| No known release-blocking regression | evidence | 0 open issues; CI and Agent Coordination green on `f7f53cd` |
| Changelog accurately describes changes since `0.1.0a2` | automated | 29 entries under `[Unreleased]`; `tests/architecture/test_release_governance.py` enforces structure and references |
| Version references are internally consistent | automated | all seven first-party packages declare `0.1.0a2` |

Optional, also satisfied: **baseline benchmarks published** — four recorded
baselines under `docs/benchmarks/`.

---

## Remaining gates

### 1. Public documentation reflects the implementation — `NEEDS_REVIEW`

`README.md`, `packages/agnara/README.md` and `examples/quickstart.py` describe
the **`0.1.0a2` published surface** and pin `pip install agnara==0.1.0a2`. The
subsystems added since then — Explorer, machine-readable discovery, CLI
introspection and generators, the project manifest, the telemetry port and its
OpenTelemetry metrics and span bridges — are documented in `docs/` and in ADRs
0051–0061, but the user-facing entry points still frame the project at `a2`.

`docs/MAINTAINERS_RELEASE.md` places version-reference updates on the release
branch, so **this gate closes during release preparation**, not before it.

### 2. Security and release checks required by `QUALITY_GATES.md` — `NEEDS_REVIEW`

`QUALITY_GATES.md` scopes its security list to *"before any release beyond
experimental alpha"*. Whether `0.1.0a3` is still inside that exemption is a
maintainer decision. Observed state on 2026-09-05:

| Requirement | Observed |
| --- | --- |
| Security boundary tests | **present** — Explorer authorization and cache-control, MCP authorization, policy ordering, redaction |
| Threat model | **absent** — `BACKLOG.md` EPIC 10 lists it unchecked |
| Dependency audit | **absent** — no tooling configured |
| Secret scanning | **disabled** — GitHub repository setting |
| Static analysis (CodeQL or equivalent) | **absent** — no workflow |
| Private vulnerability reporting | **not configured** — `SECURITY.md` says to configure it before public release |

This tool reports the facts and refuses to decide. Nothing here weakens
`QUALITY_GATES.md`: if the maintainer judges that `0.1.0a3` is beyond
experimental alpha, these become blocking and the gate stays open.

---

## Blocking issues

None in the code. Both remaining gates are judgment or release-preparation
work; no defect, regression or failing check blocks `0.1.0a3`.

---

## Recommended next work

**Single most important objective: decide the security scoping question for
`0.1.0a3`.** It is the only gate that cannot be closed by preparing the
release, and it determines whether `a3` can close at all.

- If `0.1.0a3` stays inside the experimental-alpha exemption, the remaining
  work is the documentation pass, which belongs on the release branch, and
  `a3` can close immediately after it.
- If it does not, `a3` needs a threat model, a dependency audit, secret
  scanning enabled, static analysis and a private reporting channel first.

Either way, the cheapest useful next steps are enabling GitHub secret scanning
and private vulnerability reporting: both are repository settings, neither
requires code, and both are prerequisites for `0.1.0b1` regardless of the `a3`
decision.

**Feature freeze:** not recommended yet. `a3` has no code work outstanding, but
`0.1.0a4` requires reference applications that do not exist, so development
does not stop when `a3` closes.

---

## How to reproduce this

```bash
uv run python scripts/check_release_readiness.py --verbose
```

Automated gates are re-derived from the repository on every run. Evidence is
trusted only while the commit it was recorded on is still `HEAD` — evidence
recorded on an older commit is reported `STALE`, so this page cannot quietly
outlive the code it describes.
