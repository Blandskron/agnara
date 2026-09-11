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
