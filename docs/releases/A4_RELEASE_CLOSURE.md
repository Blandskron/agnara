# 0.1.0a4 Release Closure Cycles

This document turns the remaining `0.1.0a4` work into bounded review cycles.
It does not authorize a release and does not replace
`docs/releases/RELEASE_PLAN.md`, `QUALITY_GATES.md` or the owner-only decisions
in `release-status.json`.

Audit baseline: `develop` at
`c160fbd34ae69a34d1159698a0cb2a3b1be5bc1c`, 2026-09-08.

## Current verdict

The candidate is technically coherent but is **not release-ready**. All seven
automated gates and all sixteen mandatory evidence gates pass. Seven manual
gates still require the release owner's judgment. External security controls
and the six new PyPI Trusted Publishers are not yet verified as ready.

## Cycle 1 — Locked runtime dependency audit

**State: complete in Issue #322.**

The audit covered the transitive runtime dependency set of all seven workspace
distributions. Workspace packages and development-only tools were excluded so
the result describes what a consumer installs, not the contributor environment.

```powershell
uv export --locked --all-packages --no-dev --no-emit-workspace `
  --no-hashes --format requirements.txt --output-file runtime-requirements.txt
uvx --from pip-audit==2.10.1 pip-audit `
  -r runtime-requirements.txt --format json --output pip-audit.json
```

Result: exit `0`; 29 locked runtime dependencies audited; zero known
vulnerabilities reported. `pip-audit` was obtained from PyPI and reported
version `2.10.1`.

Temporary evidence hashes:

- `runtime-requirements.txt`: SHA-256
  `3D5D94222E66DFA370CCBA91FC588E0E60A280F37BE6D8D9EC636F63AF10750C`
- `pip-audit.json`: SHA-256
  `A34E17810F72EAE047461DB9AF1D706B7F41EBAF3BBDED7912679FD1AABB8623`

This result is time-sensitive. Re-run it from the exact release commit after
the version/changelog cut and before tagging. A zero-result audit is evidence
only for the database and lockfile observed at execution time.

The a4 threat model was also confirmed to exist at `docs/THREAT_MODEL.md` with
named security-boundary tests. The previous readiness text claiming that no
release threat model existed was stale. Its deliberate exclusions remain part
of the owner's scope decision; in particular, it does not claim penetration,
fuzzing, cryptographic or full CLI/A2A/events review.

## Cycle 2 — Public-document consistency

**Owner: documentation/architecture maintainer. State: corrections prepared in
Issue #324; owner review pending.**

The review found stale HTTP public-surface claims in `ARCHITECTURE.md` and
`docs/MATURITY.md`, and a stale introspection proposal in `docs/API_DESIGN.md`.
Issue #324 reconciles them with ADRs 0070/0071 and the governed exports. The
migration guide now separates `0.1.0a4.dev0` from the future release, pins the
core/HTTP install commands and distinguishes source-environment docs tests
from installed-artifact evidence. Historical a3 snapshots and ADR context
remain historical; ecosystem interoperability remains research.

Local validation on 2026-09-08, CPython 3.14.6, for the Issue #324 working
tree based on `54bed7e7a9abb94e0e2689142ec859182e727803`:

- lint, format, typing and synchronized development-version checks passed;
- `uv run pytest -q -o cache_dir=dist/a4-pytest-cache` reported 3,467 passed
  and 53 expected skips (31 explicit browser-job cases and 22 inapplicable
  release-test parameterizations);
- the governed example/README/HTTP-guide import audit passed; the migration's
  old a3 import intentionally fails a raw whole-file a4 import audit;
- seven wheels and seven sdists built and passed `check_distributions.py`;
- the migration's exact offline core/HTTP installation succeeded in a fresh
  external venv, and both complete programs executed with `python -I` from
  those installed wheels.

This is local working-tree evidence, not CI approval for the pending diff or
validation of final `0.1.0a4` release artifacts. The existing base-commit CI
is green; the changed branch still needs integration review and CI. No manual
readiness gate is satisfied by this record.

Exit criteria:

1. Correct that stale architecture section without rewriting accepted design.
2. Search all public documents for equivalent a3-era composition/publication
   claims and classify each as intentionally historical or stale.
3. Run executable documentation tests and the governed public-import audit.
4. Present the exact diff to the owner for the `docs-reflect-implementation`
   and `docs-reproduce-applications` decisions.

The corrections remove the known contradictions. Acceptance of the two
documentation manual gates remains a separate owner decision.

## Cycle 3 — Repository-native security controls

**Owner: security/repository maintainer. State: implementation and validation
in Issue #326; manual security acceptance remains pending.**

GitHub settings read back on 2026-09-08:

- private vulnerability reporting: enabled;
- secret scanning: enabled;
- push protection: enabled;
- non-provider pattern and validity checks: disabled;
- Dependabot alerts and security updates: enabled;
- CodeQL Python/Actions analysis: added to required CI; first-run validation
  is tracked in Issue #326.

The non-provider-pattern enable request returned successfully but readback
still reported `disabled`; it is not recorded as enabled. Validity checks were
not enabled. Initial private API queries returned zero open secret-scanning
and Dependabot alerts; this snapshot does not prove that background scanning
has completed or that every candidate dependency is covered. No credential
values are copied into this record.

The threat model now includes the local CLI trust boundary and the two
reserved distributions in the seven-package publication set. It names the
existing dry-run, overwrite, target-validation and manifest tests without
claiming hostile-filesystem or protocol security for unimplemented adapters.

Exit criteria:

1. Decide whether the experimental-alpha exemption permits any item to remain
   disabled; record the decision and rationale without claiming general
   security.
2. Enable the accepted GitHub-native controls.
3. Add CodeQL or an explicitly equivalent least-privilege workflow if required
   by that decision, and obtain a green run on the release candidate.
4. Reconcile the threat model's exclusion of CLI and reserved distributions
   with the seven-package publication set.
5. Re-run `tests/security`, repository secret checks and the locked dependency
   audit, then attach exact-SHA evidence.

Do not hide exploitable findings in a public Issue; use private vulnerability
reporting.

## Cycle 4 — PyPI and release-environment preflight

**Owner: repository/PyPI owner. State: pending external verification.**

Only `agnara==0.1.0a3` is public today. The six adapter/reserved distribution
names are not yet on PyPI. The `pypi` GitHub Environment exists but currently
has no protection rules and permits administrator bypass. The repository API
cannot prove Pending Trusted Publisher configuration inside PyPI.

Exit criteria:

1. Confirm a Pending Trusted Publisher for each of `agnara-http`,
   `agnara-mcp`, `agnara-cli`, `agnara-telemetry`, `agnara-a2a` and
   `agnara-events` with repository `Blandskron/agnara`, workflow
   `release.yml`, environment `pypi`.
2. Decide and record whether the `pypi` environment needs required reviewers,
   wait timers, deployment-branch policy or administrator-bypass restrictions.
3. Verify the release workflow's action-version and permission posture against
   the accepted supply-chain policy.
4. Record owner evidence without exposing credentials. Do not create fallback
   API tokens or `.pypirc` files.

## Cycle 5 — Owner review of the seven manual gates

**Owner: release owner. State: pending.**

Use the evidence package, not a readiness percentage:

| Manual gate | Evidence to review |
| --- | --- |
| Documentation reflects implementation | README, migration guide, a4 release notes, package READMEs, executable docs tests |
| Security/release checks | Threat model, Cycle 1 audit, Cycle 3 posture, private reporting |
| Public API is sufficient | A4-14 clean-room consumer and governed API manifest |
| DI works naturally | A4-14 singleton provider construction and execution |
| Capabilities declare cleanly | A4-14 application source and result |
| CLI/introspection help materially | installed CLI smoke plus clean-room introspection |
| Documentation reproduces applications | A4-14's documentation-only construction record |

For every gate, record `accepted` or `rejected` with a short rationale. A
rejection becomes a new bounded Issue and invalidates only the evidence it
actually affects. Only the owner may change a manual gate to `SATISFIED`.

## Cycle 6 — Authorized release execution

**Owner: release owner. State: blocked by Cycles 2–5.**

Once every mandatory gate and external prerequisite is satisfied:

1. Create `release/v0.1.0a4` from the exact accepted `develop` commit.
2. Use `scripts/set_workspace_version.py release 0.1.0a4`; do not edit package
   versions or first-party pins manually.
3. Cut the dated changelog section, open a fresh `[Unreleased]`, and update
   comparison links.
4. Re-run the full quality, security, package-build, archive, installed-wheel,
   clean-room and supported-platform gates on the release commit.
5. Open the release PR to `main`. Merge only after required CI and the review
   gate pass.
6. With separate explicit owner authorization, create the immutable annotated
   `v0.1.0a4` tag on the accepted `main` commit. Let `release.yml` publish the
   exact validated fourteen artifacts through OIDC.
7. Verify all seven PyPI projects and the GitHub Release, then propagate the
   release-only commit back to `develop` before selecting a5.

No step in Cycles 1–5 authorizes Cycle 6 automatically.

## Deferred beyond a4

Do not pull these into release closure:

- streaming, execution identity, executable idempotency and performance
  budgets belong to `0.1.0a5`;
- framework interoperability and host-framework integration belong to
  `0.1.0b1`;
- production readiness, stable API and a complete security program are not a4
  claims.
