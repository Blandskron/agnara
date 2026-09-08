# Release Status

Current target: **0.1.0a4 — Application Alpha**.
Previous published release: **0.1.0a3**, published 2026-09-06 and verified on
PyPI.

Assessed 2026-09-08 from source candidate
`575d944a481f38598a290df8ba8c6cf0c72cbc2d`. A4-R2 corrected public
documentation; A4-R3 added required CodeQL and refreshed the affected quality,
packaging and security evidence. A4-R4 then re-audited the whole candidate
independently and corrected the MCP composition documentation. Earlier
external-consumer evidence remains valid only for its unchanged covered paths.

The readiness program reports **IN_PROGRESS**. The automated and recorded
engineering/application evidence is green, but seven mandatory manual gates
still require the owner's explicit judgment. `0.1.0a4` is therefore **not
release-ready** and this repository must not be tagged, published, merged to
`main` or advanced to the next target yet.

## Evidence now established

### A4-13 engineering and packaging audit

Issue [#317](https://github.com/Blandskron/agnara/issues/317) records the exact
candidate SHA, commands and results:

- 3,467 tests passed; 53 browser cases were intentionally assigned to the
  dedicated browser CI job;
- 613 architecture tests passed;
- focused HTTP/MCP/schema/policy/failure/observability selections passed;
- seven wheels and seven sdists built and passed archive and installed-artifact
  validation at `0.1.0a4.dev0`;
- a fresh external CPython 3.14 environment installed all seven wheels;
- Ubuntu, macOS and Windows jobs plus the required aggregate CI passed on the
  exact candidate SHA; and
- bounded performance sanity checks showed no catastrophic regression and make
  no a5 budget or comparative claim.

### A4-14 clean-room consumer audit

Issue [#318](https://github.com/Blandskron/agnara/issues/318) records the
external environment, artifact hashes, documentation sources and results. A
compact consumer installed the wheels without editable or workspace resolution
and proved direct, HTTP and MCP composition, dataclass schema materialization,
DI, declared-scope policy, structured failures, introspection and lifecycle
events. Three clean-room tests passed. Static scans found zero private imports
and zero monkey patches; no framework deficiency or workaround was found.

The nine numbered `agnara-project` repositories remain frozen historical
references for a2/a3. The final audit confirmed that every checkout is clean,
still points at its last successful-CI SHA and predates the a4 candidate. They
were not modified to manufacture compatibility. Three deliberately retain old
private or renamed a2/a3 imports, which is why current a4 compatibility evidence
comes from the clean-room consumer and the migration guide instead.

### A4-R4 independent closure audit

A full re-audit on 2026-09-08 treated the recorded evidence as a claim to test
rather than a result to inherit. It re-derived every automated gate, re-ran the
engineering baseline (`uv sync --locked`, Ruff lint and format, `ty`, and the
full suite at 3,470 passed with 53 expected skips), rebuilt seven wheels and
seven sdists, and reproduced the locked dependency audit with `pip-audit`
2.10.1 over 29 runtime dependencies with zero known vulnerabilities.

External consumption was revalidated against the rebuilt artifacts, not the
checkout: a wheel-only CPython 3.14 environment with the index closed, no
editable install, no workspace resolution and nothing from the repository on
`sys.path`. A 21-check clean-room consumer covered application creation,
capability declaration, dependency injection, compilation, direct invocation,
introspection with scope filtering, HTTP exposure, MCP exposure, schema
projection, policy, structured failures and cross-surface exposure coherence.
A 13-probe adversarial suite covered traversal, header injection, nesting
limits, redaction, anonymous fail-closed behavior, forged identity, media-type
confusion, the ASGI protocol boundary and runtime-owned parameter names. The
installed CLI answered `inspect`, `graph`, `context` and `schema openapi`, and
its exported OpenAPI document was byte-identical to what the ASGI application
serves.

Two defects were found and fixed. The `agnara-mcp` README documented `plans`
without showing how to build it, which left the consumer-facing document for
that distribution unusable on its own; the fix adds an executable
"Execution plans" section and registers it in `tests/docs`. The optional
benchmark gate cited a pre-squash commit absent from history, so it reported
stale rather than green; it is re-anchored to the commit that last changed what
it covers, without re-measuring baselines on incomparable hardware. Fixing the
README changed `packages/`, which correctly expired the twelve evidence records
covering it; each was re-established at the new candidate and is re-anchored
there. Required cross-platform CI has not yet run on that commit.

No framework, packaging or public-API deficiency was found, and the clean-room
application needed no workaround, no internal import and no monkey patch.

## Derived gate state

Run the checker for authoritative per-gate detail:

```bash
uv run python scripts/check_release_readiness.py --verbose
```

| Group | State |
| --- | --- |
| Automated gates | 7 satisfied; re-derived on every run |
| Evidence gates | 16 satisfied with commit and coverage records |
| Manual gates | 7 need owner review |
| Optional benchmark gate | satisfied; re-anchored from a dangling pre-squash SHA |

The expected derived status remains `IN_PROGRESS`, not `RELEASE_READY`. Manual
gates are never inferred from passing tests or from agent judgment.

## Owner decisions required

The release owner must explicitly decide and record:

1. public documentation reflects the implementation;
2. the experimental-alpha security/release posture satisfies
   `QUALITY_GATES.md`. The a4 threat model and its named boundary tests exist;
   a locked audit of 29 runtime dependencies found zero known vulnerabilities
   on 2026-09-08; repository security tests pass; and private reporting is
   enabled. Cycle 3 enabled GitHub secret scanning/push protection and
   Dependabot alerts/security updates. Required Python/Actions CodeQL analysis
   passed with zero results in Issue #326. Non-provider patterns and validity checks
   remain disabled; the manual security decision remains pending;
3. the public API is sufficient for the demonstrated applications;
4. dependency injection works naturally;
5. capabilities can be declared cleanly;
6. CLI and introspection materially help a developer; and
7. the documentation is sufficient to reproduce the application.

The owner package for those decisions is:

- draft release notes: [`v0.1.0a4.md`](v0.1.0a4.md);
- migration guide: [`../MIGRATION_a3_to_a4.md`](../MIGRATION_a3_to_a4.md);
- curated delta: [`../../CHANGELOG.md`](../../CHANGELOG.md) `[Unreleased]`;
- engineering evidence: Issue #317;
- clean-room evidence: Issue #318; and
- this derived gate record plus `release-status.json`; and
- the bounded [`A4_RELEASE_CLOSURE.md`](A4_RELEASE_CLOSURE.md) cycle plan.

## Publication control and external prerequisites

The publication baseline is `agnara==0.1.0a3`; the six new names await their
first synchronized publication. On 2026-09-08 the owner confirmed that the six
Pending Trusted Publishers are not configured. This is a publication blocker;
Cycle 4 lists the exact fields to configure and verify. Private vulnerability
reporting is already enabled.

After all manual decisions and external prerequisites are recorded, release
preparation may cut versions and changelog on a release branch and re-run the
documented gates. Publication must still be a separate explicit owner action:
an immutable annotated tag, the protected workflow, OIDC Trusted Publishing and
exactly the validated fourteen artifacts. No fallback token, manual upload or
silent artifact rebuild is acceptable.

## Reproduce

```bash
uv run python scripts/check_release_readiness.py --verbose
uv run python scripts/check_release_readiness.py --json
uv run python scripts/check_release_readiness.py --require-ready
```

The first two commands must agree. The third must exit non-zero while any
mandatory manual gate remains pending. Evidence expires when a covered path
changes from its recorded commit to `HEAD`; records without coverage expire on
any commit.
