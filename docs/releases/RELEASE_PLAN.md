# Agnara Release Plan

## Baseline and target

`0.1.0a8` is the sole retained publication baseline. It proved the reviewed,
dispatch-driven seven-distribution publication path; it is not the compatibility
or product contract this project will publish next.

The next and first planned product release is **`1.0.0`**. There will be no
additional interim publication cadence. Development
continues on `develop` until the stable gates below have evidence.

## Release thesis

`1.0.0` proves that Agnara's capability runtime and its documented public
surface are stable enough for production adoption. It must not be cut merely
because a subsystem milestone is complete.

The work leading to it includes streaming semantics, execution identity and
operational idempotency; performance budgets enforced in CI; interoperability
and composition evidence; security-program evidence; a stable public API; and
repeatable publication of all seven distributions.

## Gates

All existing quality, security, packaging and review requirements remain in
force. The `1.0.0` release additionally requires evidence for each item below.

| Gate | Evidence |
| --- | --- |
| Execution semantics | Streaming, identity and idempotency have accepted designs, implementations and conformance tests. |
| Performance | Budgets cover compiled execution paths and regressions fail CI. |
| Interoperability | Standalone, hosted, embedded and side-by-side scenarios satisfy the approved contract. |
| Security | Threat model, dependency/supply-chain checks and security invariants have current evidence. |
| Public API | Every public export is classified stable or deprecated with migration guidance. |
| Documentation | A clean-room application can be built from supported documentation alone. |
| Publication | The A8 workflow builds, verifies and publishes all distributions from the accepted `1.0.0` commit. |

`docs/releases/release-status.json` records current gate state.
`QUALITY_GATES.md` and `docs/MAINTAINERS_RELEASE.md` own the operational
procedure; this plan owns only the product bar.

## Scope lock and gate ownership

V1-02 turns these release gates into an execution plan. The table does not
change a gate's status: `release-status.json` remains the sole current-status
record, and CI remains authoritative for its assigned checks. Task identifiers
refer to the 1.0 work program; each becomes a GitHub Issue before implementation.

| Mandatory gate | Responsible work | Required evidence | Freshness and human decision |
| --- | --- | --- | --- |
| Python baseline | V1-33, V1-44 | Python 3.14 CI, built-wheel and installed-import verification. | Re-derived on every candidate SHA; CI verifies platform coverage. |
| Changelog accurate | V1-43, V1-44 | Clean-room migration result, dated release notes and checked comparison links. | Re-run when public behavior or release notes change; a maintainer reviews the final narrative. |
| Version consistency | V1-33, V1-44 | `set_workspace_version.py --check`, exact adapter pins and current lockfile. | Re-run after every version, dependency or lockfile change and at the version cut. |
| Repository clean / release commit identified | V1-44 | Clean release-branch checkout and recorded accepted `main` SHA. | Re-derived immediately before release dispatch. |
| License metadata | V1-33, V1-37, V1-44 | Source and built-artifact metadata checks for all seven distributions and third-party asset licenses. | Re-run when package metadata, packaged assets or dependencies change. |
| Public API distinguished | V1-31–V1-33 | Exact manifest, consumer import audit, installed-artifact reference and migration guidance. | Re-run when an `__all__`, public manifest, example or public documentation changes; maintainers decide stable/deprecated disposition. |
| Publication prerequisites | V1-44 | Seven-distribution build, clean install, Trusted Publisher readback and protected-environment rehearsal. | Development is correctly `PARTIAL`; rerun only at the version cut and after packaging or registry configuration change. |
| Execution semantics | V1-03–V1-06, V1-10–V1-20 | Accepted decisions plus normal, failure, cancellation, race and conformance tests for streams, identity, idempotency and composition. | Rerun when execution, policy, adapter projection or concurrency paths change; maintainers review closure. |
| Performance budgets | V1-39–V1-41 | Reproducible methodology, raw samples, calibrated budgets and an intentional CI fail/pass proof. | Rebenchmark after measured-path, interpreter, serializer, server or methodology change; human approval sets budgets. |
| Interoperability | V1-21–V1-30 | Approved host contract, common conformance harness and the required scenarios in `docs/INTEROPERABILITY.md` section 6A. | Re-run each fixture when its host version, bridge or covered kernel contract changes; support is a maintainer decision. |
| Security program | V1-34–V1-38 | Current threat model, abuse/failure tests, dependency audit, supply-chain evidence and private finding disposition. | Re-run when trust boundaries, dependencies, CI security configuration or covered code change; alert disposition remains human review. |
| Stable public API | V1-31–V1-33 | Per-export stable/deprecated/removal decision, compatibility policy and migration guidance. | No provisional export is promoted by default. A maintainer makes the final commitment. |
| Clean-room documentation | V1-42, V1-43 | A clean-room application built only from supported docs, plus full quality evidence. | Re-run after supported docs, CLI/scaffolding or public API changes; maintainer reviews the result. |
| Publication rehearsal | V1-44 | Release-branch rehearsal of all seven artifacts and protected-publisher controls without an unauthorized upload. | Re-run at the final version cut; the protected environment remains the human authorization boundary. |
| Final release audit | V1-45 | Independent review of the exact candidate, all gate evidence and artifact hashes. | Must name the candidate SHA and current artifacts; cannot be inherited from an earlier commit. |

## Public-surface commitment

The seven reviewed distributions remain the publication set. Their 292 current
public exports are all provisional today; none becomes stable through this
scope lock. V1-31–V1-33 must explicitly classify every release-set export as
stable, deprecated with migration guidance, or removed before the 1.0
compatibility gate can close. The empty `agnara-a2a` and `agnara-events`
namespaces have no export to stabilize. New experimental integrations and all
private documentation, Explorer and discovery implementation modules are
outside the stable public contract unless a later reviewed public-surface change
adds them.

## Evidence rerun rules

Automation re-derives automated gates on each SHA. Evidence records must name
the commit, covered paths, command, dependency or fixture versions and artifact
hashes where applicable. A change to a covered path makes the record stale and
requires a rerun; a skipped local or CI-only check is recorded as `NOT RUN` or
`NEEDS CI`, never as a pass. Human review is required for architectural closure,
security-alert disposition, compatibility commitment, integration support and
protected publication authorization.
