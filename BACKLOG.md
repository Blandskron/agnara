# Backlog

This file owns decomposed work ready to implement on the path to `1.0.0`.
`ROADMAP.md` owns the destination and `docs/INITIATIVES.md` owns dependency
order.

## Ready after design acceptance

- [ ] Implement the accepted protocol-neutral streaming model (I2).
- [ ] Implement execution identity and operational idempotency (I3).
- [ ] Establish performance budgets and CI regression gates (I14).
- [ ] Complete interoperability and composition contracts (I20, I8).
- [ ] Complete the security program evidence (I10).

<<<<<<< HEAD
## A8

Bootstrap identity correction (#332): distinct OIDC environments per distribution;
GitHub setup and workflow validation do not certify the pending PyPI readbacks.

Release pipeline recovery only (ADRs 0082 and 0083). Everything below `## A8` stays out.

- [~] E0B.12 Document release and hotfix automation evidence. The release half
  gains real evidence here: `0.1.0a4` exercised the tag pipeline through to a
  rejected upload, `0.1.0a5` and `0.1.0a7` proved the sequenced preflight
  aborts before upload, and `0.1.0a6` proved that a mistaken human publisher
  readback can still reach and fail the first upload. All four were tagged
  before the gates ran; `0.1.0a8` is the first release whose tag can only be
  created by an approved, fully gated `workflow_dispatch` run. The hotfix half
  is still unexercised, so the item does not close.

- [~] Owner action, phased because PyPI allows three pending publishers at a
  time (ADR 0083): `bootstrap-1` publishers `agnara-a2a` / `pypi-a2a`,
  `agnara-cli` / `pypi-cli` and `agnara-events` / `pypi-events` were read back
  on `2026-09-09` and are recorded `VERIFIED` in
  `docs/releases/publication.json`. Still open: after `bootstrap-1` runs,
  create and read back `agnara-http` / `pypi-http`, `agnara-mcp` / `pypi-mcp`
  and `agnara-telemetry` / `pypi-telemetry` (phase `bootstrap-2`), then the
  active `agnara` / `pypi-core` publisher (phase `final`); each readback dated
  on or after `2026-09-08`, signed by a human account.

- [!] Owner action: protect the `pypi` GitHub Environment with at least one
  required reviewer and a deployment branch policy limited to `main`.
  `scripts/check_release_preconditions.py` refuses the release until both
  exist. Do not enable *prevent self-review* while the dispatching owner is
  the only reviewer.

- [ ] Owner action: create a tag ruleset for `v*` that blocks update and
  deletion (immutability). Do not restrict creation: the approved workflow run
  is the only creator.

- [ ] Owner action: yank `agnara 0.1.0a4` once `0.1.0a8` is published and
  verified complete. Reason: `Partial multi-distribution publication;
  superseded by 0.1.0a8.`

## A9
=======
## Deferred decisions
>>>>>>> 15cdde3ccb0211665dc88e153872be1acdeee5aa

- [ ] D7 Decide whether `agnara.core.di` remains the public dependency
  injection spelling before API stabilization.
- [ ] D6 Rename the introspection snapshot field `.apps` to `applications`
  only with an intentional snapshot-format migration.
- [ ] Configure an independent reviewer identity when one is available.

No item in this backlog authorizes a publication before the `1.0.0` release
gates are satisfied.
