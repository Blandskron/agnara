# Backlog

Legend:

- [ ] Not started
- [~] In progress
- [!] Blocked
- [?] Research

This file owns **decomposed work that is ready to implement**. It does not own the long-term plan: ROADMAP.md owns where Agnara is going.

## A5

- [?] E2.7 Benchmark adapters before selecting defaults.

- [~] Security threat model present. Partial: `docs/THREAT_MODEL.md` covers the
  a4 surface -- assets, boundaries, abuse cases, verified protections with
  their evidence, and delegated assumptions -- and `tests/security/` regresses
  it. It is not the beta security program: no fuzzing, penetration test or
  dependency vulnerability scan stands behind it. `I10`.

- [ ] API docs present. Partial: `docs/API_DESIGN.md` records intent, and
  there is no generated reference for the 41 public names. `I9`, then `I18`.

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

