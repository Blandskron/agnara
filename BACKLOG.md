# Backlog

Legend:

- [ ] Not started
- [~] In progress
- [!] Blocked
- [?] Research

This file owns **decomposed work that is ready to implement**. It does not own the long-term plan: ROADMAP.md owns where Agnara is going.

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

- [!] Owner action: on PyPI, delete any pending entry whose Project name is not
  exactly `agnara-a2a` and recreate it; read back the Project name and the
  shared tuple (GitHub Actions, `Blandskron`, `agnara`, `release.yml`, `pypi`)
  for all seven entries; record each readback in
  `docs/releases/publication.json` (schema 3) dated on or after `2026-09-08`,
  signed by a human account, with `status: VERIFIED`.

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

- [?] E2.7 Benchmark adapters before selecting defaults.

- [~] Security threat model present. Partial: `docs/THREAT_MODEL.md` covers the
  a4 surface -- assets, boundaries, abuse cases, verified protections with
  their evidence, and delegated assumptions -- and `tests/security/` regresses
  it. It is not the beta security program: no fuzzing, penetration test or
  dependency vulnerability scan stands behind it. `I10`.

- [ ] API docs present. Partial: `docs/API_DESIGN.md` records intent, and
  there is no generated reference for the 41 public names. `I9`, then `I18`.

- [ ] Migration policy for alpha documented. **Absent.** Needed before any API
  is called stable. `I9`.

- [ ] E0B.9 Configure independent reviewer identity when available.

- [ ] E0B.12 Document release and hotfix automation evidence.

- [ ] D7 Decide whether `agnara.core.di` is the right public spelling for
  dependency injection. It is the second import in the README and in
  `examples/quickstart.py`, so `core` — a word that reads as an internal
  namespace — sits on the first screen a new user sees, and an external
  application cannot avoid it. Found while governing the subpackage surfaces
  (#275) and deliberately left alone there: a rename is a breaking change with
  a migration cost, and it does not belong inside a change whose purpose is to
  make the current surface visible rather than to alter it. Decide with the
  `0.1.0a4` external evidence, which will show whether the spelling actually
  confuses anyone, and before any name is considered for `stable`. First
  evidence: eight of the nine reference applications import `agnara.core.di`,
  at 35 sites, and none found a way around it — it is the most imported module
  of the core after the top-level package.

- [ ] D6 `.apps` means two things. On `ApplicationDescriptor` it is the
  bounded contexts an application mounts (E1A.4); on `IntrospectionSnapshot`
  it is a tuple of whole applications, which ADR 0011 says are not apps. #260
  renamed the misleading *type* but not the field, because a field name is
  part of the serialized document and changing it needs an
  `INTROSPECTION_VERSION` bump. Rename it to `applications` in the next
  snapshot format change rather than separately.

