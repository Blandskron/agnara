# ADR 0083: Distinct OIDC identities for the A8 PyPI bootstrap

- Status: Proposed (implementation requested by the repository owner)
- Date: 2026-09-09
- Release: `0.1.0a8`; tracking: #332
- Amends ADR 0082's shared publisher tuple and publishing job, not its tag order.

## Evidence and root cause

Authenticated PyPI readback on 2026-09-09 confirmed an active `agnara`
publisher and a pending `agnara-a2a` publisher using
`Blandskron / agnara / release.yml / pypi`. Adding `agnara-cli` with that
identity was rejected because it already belonged to another pending project.
[Warehouse #20074](https://github.com/pypi/warehouse/pull/20074) documents
the database uniqueness constraint on owner/repository/workflow/environment.
Different canonical project names do not distinguish pending identities.

The previous preflight therefore required an impossible simultaneous setup.
This is a registry bootstrap defect, not a need for PyPI API tokens.

## Decision

Keep `release.yml` as the direct caller of every SHA-pinned publishing action.
Do not use reusable workflows for uploads. Keep all versions at `0.1.0a8`.

All publishers use GitHub owner `Blandskron`, repository `agnara`, and
workflow filename `release.yml`. Their bootstrap environments are:

| Canonical PyPI project | Publisher kind before A8 | Environment |
| --- | --- | --- |
| `agnara` | active | `pypi-core` |
| `agnara-a2a` | pending | `pypi-a2a` |
| `agnara-cli` | pending | `pypi-cli` |
| `agnara-events` | pending | `pypi-events` |
| `agnara-http` | pending | `pypi-http` |
| `agnara-mcp` | pending | `pypi-mcp` |
| `agnara-telemetry` | pending | `pypi-telemetry` |

The protected `pypi` environment remains the single human authorization gate
with reviewer `Blandskron` and `prevent_self_review: false`. Its `publish` job
has only `contents: read` and rechecks the release preconditions after approval.
Each subsequent publishing job has its own environment and exactly
`contents: read` plus `id-token: write`. Every environment accepts only the
branch `main`; none contains secrets. The bootstrap environments need no
additional reviewer because they unconditionally depend on the human gate.

The dependency chain is:

```text
dispatch -> quality/preconditions -> build -> clean-room -> preflight
 -> publish (human pypi approval, no OIDC)
 -> publish-a2a -> publish-cli -> publish-events -> publish-http
 -> publish-mcp -> publish-telemetry -> publish-core
 -> verify-published (7 wheels + 7 sdists, install/import)
 -> tag -> GitHub Release
```

### Phases (amendment of 2026-09-09)

PyPI also caps an account at **three** Pending Trusted Publishers at a time,
so the six pending identities above cannot exist simultaneously. The chain is
therefore run as three dispatches of `release.yml`, selected by a `phase`
input; the only `if:` conditions in the workflow select the phase, and every
other dependency stays a real `needs`:

| Phase | Uploads (in order) | Verification | Tag / Release |
| --- | --- | --- | --- |
| `bootstrap-1` | `agnara-a2a`, `agnara-cli`, `agnara-events` | those three complete on PyPI | none |
| `bootstrap-2` | `agnara-http`, `agnara-mcp`, `agnara-telemetry` | the six adapters complete | none |
| `final` | `agnara` | all seven complete, then a clean install | `v<version>`, then the GitHub Release |

`check_publication_readiness.py --phase` requires the human readback only for
the projects the phase uploads -- the publishers of a later phase cannot exist
yet -- and treats the index as the evidence for earlier phases: their projects
must be complete at the version, while the projects of this and later phases
must carry no file of it. No phase re-publishes another, and no phase but
`final` can create the tag or the GitHub Release. A failed upload or a failed
verification in any phase leaves no tag, because the tag job runs only in
`final` and depends on `verify-published`. The three pending slots freed by
`bootstrap-1` are what allow the `bootstrap-2` publishers to be created.

Schema 3 of `publication.json` records the common owner/repository/workflow
and an exact `publisher_environment` per canonical project. Prior confirmation
of `pypi` cannot certify a bootstrap identity. All seven remain `UNVERIFIED`
until the new tuples are read back from PyPI. Global offline and online
readiness still refuse before the first upload while any readback is missing.
No workflow may edit this record.

Each upload rechecks main/tag/approval protection, validates the entire
downloaded bundle, and checks its canonical project, environment, job name,
repository and exact `release.yml@refs/heads/main` identity before selecting
only that project's wheel and sdist. Static workflow tests bind the declared
job environment and selected artifact directory to that same mapping. PyPI
enforces the actual OIDC claims; the script does not mint or decode tokens.
The global online absence check runs before publication, not between uploads,
because earlier jobs have deliberately created files on the index by then.

## Security and failure behavior

Only upload jobs can request OIDC; none can write repository contents.
Attestations, metadata validation and SHA pinning remain mandatory. A failure
in any upload blocks later uploads, verification, the tag and the release.
There is no `skip-existing`, token fallback, automatic resume or manual tag.
Partial publication must be diagnosed against the retained artifacts; this
change does not authorize rerunning over existing files or changing version.

## Owner setup and later migration

Before A8, add the active `agnara / pypi-core` publisher and configure the six
pending publishers with the table above. The old `agnara-a2a / pypi` pending
entry does not satisfy the new readback. Read the exact project and all four
identity fields after saving; record only confirmed facts, never credentials.

After a successful A8, pending publishers become ordinary project publishers.
A separate reviewed migration can register the common
`Blandskron / agnara / release.yml / pypi` publisher on all seven existing
projects, verify it, restore a single publication identity for later releases,
then retire the bootstrap publishers/environments. Do not implement that
migration before the projects exist. No later version is prepared here.
