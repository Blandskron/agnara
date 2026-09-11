# ADR 0079 — Sequenced Publication and Publish Readiness

- Status: Proposed
- Date: 2026-09-08
- Tracking: GitHub Issue #328
- Release: `0.1.0a5`
- Amends: ADR 0073
- Related: ADR 0021, ADR 0069, ADR 0078

## Context

ADR 0073 established the seven-distribution publication set and the validation
that stands in front of it. It got everything about *building* right and one
thing about *publishing* wrong: it treated the upload as a single act. One
`pypa/gh-action-pypi-publish` invocation received `dist/` and uploaded fourteen
files, and the steps that were supposed to prove the release worked lived after
it in the same job.

`0.1.0a4` found all three consequences at once (ADR 0078):

1. **The order was an accident.** Twine sorts wheels before sdists, and within
   each group by filename, so `agnara` went first because of an ASCII
   comparison. The kernel therefore announced a version whose adapters did not
   exist, and `pip install agnara==0.1.0a4` succeeded into a set that could
   never be completed.
2. **The failure was a position in a batch**, not a named distribution, and it
   left the release half-done with no machine-readable statement of which half.
3. **Verification and the GitHub Release were steps, not jobs.** A failed
   upload cancelled both silently. The only reason no GitHub Release announced
   an unpublished release is that the same failure skipped that step too —
   which is luck, not design.

Underneath all three is one missing distinction. Everything the repository
measured answered "is the code ready". Nothing answered "is the *release*
ready", and the two are not the same question. The Trusted Publisher
configuration for six PyPI projects was known to be outstanding, written down
in two documents, and enforced by nothing.

## Decision

### 1. CODE READY and PUBLISH READY are separate, separately measured claims

`scripts/check_release_readiness.py` keeps the first. A new
`scripts/check_publication_readiness.py` owns the second: the reviewed set, the
workspace layout, synchronized versions, exact first-party pins, the lockfile,
the built artifact set, release notes, the dated changelog section, the
annotated tag and its ancestry, and the state of the registry.

`check_release_readiness.py` gains a mandatory automated gate,
`publication-prerequisites`, that runs the offline part of it, and a mandatory
manual gate, `pypi-trusted-publishers`, that no automated check can satisfy.

### 2. External registry configuration is a reviewed file, not a paragraph

`docs/releases/publication.json` records, per project and per target version,
that a human read the Trusted Publisher tuple back from PyPI — provider, owner,
repository, workflow filename, environment — and who read it and when. Any
project not `VERIFIED` for the exact target fails publish readiness, and the
release workflow refuses to upload.

This does not make the repository able to observe PyPI. It makes the repository
unable to *assume* PyPI, and it turns the confirmation into a diff on the
release branch that a reviewer sees.

### 3. The kernel is published last

Upload order is `agnara-a2a`, `agnara-cli`, `agnara-events`, `agnara-http`,
`agnara-mcp`, `agnara-telemetry`, then `agnara`. Each distribution is staged
into its own directory and uploaded by its own step, so a failure names a
distribution.

Order matters because an adapter pins its kernel exactly (ADR 0069). Publishing
the kernel last makes a partial publication **fail closed**: siblings published
without their kernel resolve for nobody, and the `agnara` version an ordinary
`pip install` sees does not move until the whole set is there. The opposite
order fails open, which is what `0.1.0a4` did.

### 4. Publication, verification and announcement are separate jobs

```text
validate → build → test-artifact → publish-preflight
        → publish → verify-published → github-release
```

`publish-preflight` reads the public index before any credential exists: it
refuses if any of the seven already carries a file at this version, and reports
which projects a pending publisher still has to create.

`verify-published` asserts **completeness**, not installability — every
distribution must carry both a wheel and an sdist at the released version — and
then installs the published set into a clean environment and exercises it.
`agnara 0.1.0a4` is installable and has no sdist; this is the check that fails
on exactly that.

`github-release` depends on `verify-published`. A successful GitHub Release can
no longer coexist with an incomplete PyPI.

### 5. `skip-existing` stays off, and a partial publication is closed by the
next version

A file that already exists at the version being published is a real condition
that means something has gone wrong. Suppressing it would make a rerun look
like a success and would hide exactly the state this ADR exists to detect.

There is deliberately **no resumable rerun**. A resumable path needs either
`skip-existing`, which hides the ordinary error, or a manual "start from
distribution N" input, which would give a dispatch-triggered run the ability to
publish — the invariant ADR 0073 decision 6 exists to protect. So the recovery
procedure for a partial publication is the one this release is itself
demonstrating: select the next version, publish the complete set, yank what was
orphaned. With the preflight and the publisher record in place, the case should
not arise; if it does, the honest answer is a new version rather than a
mechanism that makes half-publications routine.

### 6. Every action on the publication path is pinned to a full commit SHA

`actions/checkout`, `astral-sh/setup-uv`, `actions/upload-artifact`,
`actions/download-artifact`, `pypa/gh-action-pypi-publish` and
`softprops/action-gh-release`, each with the human version in a trailing
comment. A movable tag on a job holding `id-token: write` is a supply-chain
decision and was being made by default. `.github/dependabot.yml` owns moving
those pins, and excludes the publisher action from the grouped update so it is
reviewed alone.

`contents: write` moved off the publishing job entirely; only
`github-release` has it. The artifact bundle's retention went from one day to
thirty, because diagnosing a partial publication requires the exact bundle that
was uploaded, and one day was not enough for `0.1.0a4`.

### 7. One source of truth for the seven names

`docs/distributions.json` declares the reviewed set — names, import packages,
console scripts and adapter-owned third-party requirements.
`scripts/distributions.py` reads it for the release tooling and the
architecture tests, and prints it for the workflows. The seven names were
previously spelled out independently in five places and compared in one.

Canonical project names stay dash-separated. `agnara_a2a-0.1.0a5.tar.gz` is
PEP 427/625 filename normalization of `agnara-a2a`, not a naming defect, and
nothing in the release "corrects" it. Equally, a PyPI project created under a
misspelled name is not a reason to rename a distribution here: the metadata
name is canonical and the registry configuration is what gets fixed.

## Threat analysis

**A publisher misconfiguration reaching an upload.** The preflight cannot read
PyPI's publisher table, so it cannot prove the configuration is right. It can
prove nobody claimed it was, which is the failure that actually occurred, and
it can prove no file of this version exists yet.

**A tampered artifact between build and publish.** The publish job re-validates
the downloaded bundle against the reviewed set and the tagged version before
staging, and the digests recorded at build time are retained for ninety days.

**A compromised third-party action.** SHA pinning removes tag mutation from the
threat model for the publication path. It does not remove a compromised commit,
which is why the publisher action is reviewed separately from grouped updates.

**Announcing a release that does not exist.** Structurally impossible now: the
job that creates the GitHub Release depends on the job that proves every
distribution is complete on the index.

**A partial publication that fails open.** Addressed by ordering, not by
hoping. The kernel moves last, so the worst reachable state is a set of
siblings nothing can resolve.

## Consequences

- A release can no longer report success while PyPI is incomplete.
- The owner has one more required, reviewable action before tagging: filling in
  `docs/releases/publication.json`. That is the point.
- Seven upload steps replace one, and each is a separate OIDC exchange against
  the same environment. The `pypi` environment is entered once, so an approval
  rule still asks once.
- Adding or removing a distribution now means editing one JSON file, the
  workflow's publish steps, and an ADR — and the test suite fails until the
  three agree.
