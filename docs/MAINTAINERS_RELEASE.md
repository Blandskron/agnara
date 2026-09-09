# Releasing Agnara to PyPI

Agnara follows a highly automated, secure release pipeline designed to prevent
accidental or malicious publications — and, since `0.1.0a8`, designed so that
a release can no longer consume a version before every gate has passed and a
human has approved it.

The reviewed publication set is the seven synchronized first-party
distributions declared in [`docs/distributions.json`](distributions.json) and
decided in ADR 0073. `agnara` is the kernel; HTTP, MCP, CLI and telemetry are
usable adapters, while A2A and events are explicitly reserved namespaces with
zero public names.

That JSON file is the **single source of truth** for the seven names, their
import packages, their console scripts and their adapter-owned third-party
requirements. The release scripts, the architecture tests and both workflows
read it; `tests/release/test_publication_set.py` fails when any of them
disagrees. Do not retype the list.

## 0. CODE READY is not PUBLISH READY, and neither is a tag

Three different claims, which fail for different reasons. Conflating the first
two is how `0.1.0a4` published one of fourteen artifacts. Treating the third
as the *start* of a release is how `0.1.0a4` to `0.1.0a7` each consumed a
version without publishing. Read
[ADR 0079](adr/0079-sequenced-publication-and-publish-readiness.md) and
[ADR 0082](adr/0082-dispatch-driven-release-with-the-tag-as-a-consequence.md)
before running a release.

| Claim | Owner | Question |
| --- | --- | --- |
| CODE READY | `scripts/check_release_readiness.py` | Is the implementation mature enough to close this release? |
| PUBLISH READY | `scripts/check_publication_readiness.py` | Can this exact commit become seven complete distributions on the index? |
| RELEASED | the approved `release.yml` run | Did every gate pass, did a human approve, and did the index confirm all fourteen files? |

```bash
uv run python scripts/check_release_readiness.py --verbose
uv run python scripts/check_publication_readiness.py --version <version>
uv run python scripts/check_publication_readiness.py --version <version> --online
```

The `--online` form reads the public index. Before publishing it refuses if any
project already carries a file at that version, and if the recorded publisher
kind disagrees with whether the project exists; after publishing,
`--require-published` requires every project to carry both a wheel and an sdist.

**The tag is not a step you take.** `v<version>` is created by the release
workflow itself, on the dispatched `main` commit, only after every gate has
passed and a reviewer has approved the run. There is no `git tag` in this
document, and a tag pushed by hand publishes nothing.

## 1. Quality Gates and Release Readiness

Before a release is drafted, the repository must pass all automated quality
gates:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

The workspace has no `[dev]` extra: development dependencies live in the root
`[dependency-groups] dev` table and are installed by `uv sync`. `uv` itself is
a required release tool — `tests/http/test_documentation_assets.py` asserts it
is on `PATH`.

When 100% green, the framework is **CODE READY**. That is one third of the
answer.

### Licensing Readiness Check

- [x] LICENSE exists
- [x] Apache-2.0 selected
- [x] package metadata declares Apache-2.0
- [x] wheel contains required license metadata/files
- [x] sdist contains required license metadata/files
- [x] README license documentation is consistent
- [x] no contradictory "license pending" documentation remains

## 2. Trusted Publishing, and the record that proves it was checked

Agnara uses **PyPI Trusted Publishing via OpenID Connect (OIDC)**. No passwords,
tokens or `.pypirc` files are ever stored in the repository or in personal
environments.

Every one of the seven projects needs the identical publisher tuple:

| Field | Value |
| --- | --- |
| Provider | GitHub Actions |
| Owner | `Blandskron` |
| Repository | `agnara` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

A project that does not exist yet needs a **pending** publisher, added at
<https://pypi.org/manage/account/publishing/>; it creates the project on first
upload and does not reserve the name. A project that already exists carries an
**active** publisher in its own Publishing settings. Today `agnara` exists and
the six siblings do not, so the record says `active` once and `pending` six
times, and the online preflight refuses if the index disagrees.

**Verify by reading the Project name and the four fields back, per project.**
A 404 on the project page proves nothing about whether a pending publisher
exists. PyPI answers a name mismatch with `400 Non-user identities cannot
create new projects` — that is what `0.1.0a4` and `0.1.0a6` received for
`agnara-a2a`, and the `0.1.0a6` readback had been recorded as verified. Read
the Project name field character by character: `agnara-a2a`, never
`agnara_a2a`, which is only the wheel and sdist filename normalization.

Record each readback in
[`docs/releases/publication.json`](releases/publication.json) (schema 2):
`trusted_publisher: VERIFIED`, `publisher_kind` (`pending` or `active`),
`verified_by` (a human account — automation identities are refused) and
`verified_on` (an ISO date on or after `last_registry_failure.on`). Then set
`status`, `confirmed_by` and `confirmed_on` at the top. The file records
registry facts; it no longer carries a per-release `target`, because the
per-release authorization is the environment approval in section 4, and a JSON
field cannot stop a tag that already exists.

`check_publication_readiness.py` fails while any project is `UNVERIFIED`,
while any readback predates the last registry failure, while the recorded
tuple is not the identity `release.yml` presents, or while a publisher kind
disagrees with the index. `release.yml` runs it before anything is built,
before the approval gate and again before the first upload — and no tag exists
until all of that has passed.

If a project was created under a misspelled name, the fix is on PyPI: delete the
wrong project, remove the wrong publisher, re-register under the exact canonical
name. Never rename a distribution here to match a registry typo.

## 3. How to prepare a release

Everything in this section is a reviewable pull request. Nothing in it
publishes, and nothing in it creates a tag.

ADR 0021 keeps every first-party package on one synchronized version, so a
release updates all seven, not only the published one. ADR 0069 additionally
requires every adapter to pin that exact core version; these thirteen values are
changed only through the workspace transition tool.

1. Branch `release/v<version>` from `develop` (or from `main` for a recovery
   release that carries the runtime unchanged).
2. Set `current_target` in `docs/releases/release-status.json`, then
   `python scripts/set_workspace_version.py release <version>` — validates the
   complete workspace before writing, updates all project versions and adapter
   core pins, and refreshes `uv.lock` as one operation.
3. `python scripts/set_workspace_version.py release <version> --check`.
4. Close `CHANGELOG.md`: rename `[Unreleased]` to `[<version>] - YYYY-MM-DD`,
   open a new empty `[Unreleased]`, and update the comparison links.
5. Write `docs/releases/v<version>.md`. This is the GitHub Release body; the
   generated PR list is appended under it. A missing file fails publish
   readiness rather than degrading the notes silently.
6. Record the publisher readbacks from section 2 in
   `docs/releases/publication.json`.
7. Build all seven wheels and sdists, run `scripts/check_distributions.py`
   against the artifact directory, then install adapter-owned third-party
   dependencies and all seven local wheels into a clean environment with index
   access closed, and run the checker with `-I`.
8. `scripts/check_publication_readiness.py --version <version> --dist dist/`,
   then the `--online` form.
9. Open the PR to `main`, wait for every required check, and merge through the
   mechanism branch protection allows.

## 4. How to run a release

1. Open **Actions → Release to PyPI → Run workflow**.
2. Select branch **`main`** and enter the version, e.g. `0.1.0a8`. It must
   equal the synchronized workspace version on `main`.
3. Press **Run workflow**.
4. When the run reaches `approve-and-tag`, GitHub asks the required reviewers
   of the `pypi` environment to approve. Review the run's logs — every gate
   above it is green by construction — and approve. The run creates the
   annotated tag on the dispatched commit.
5. When the run reaches `publish`, approve once more. The run uploads the
   seven projects, verifies the index and creates the GitHub Release.

Two approvals are deliberate: the first authorizes the one irreversible act on
the repository, the second the irreversible act on the index, and each job
keeps only the permission it needs.

If the run refuses before the approval, read the `::error::` lines: `main`
moved since you dispatched (dispatch again from its head), the tag already
exists (that version is spent — choose the next), the environment is not
protected (section 5), or the publication record is not verified (section 2).
Nothing irreversible has happened at that point.

### The `release.yml` pipeline

Nine jobs, chained by real `needs`, so a failure at any point stops everything
after it:

```text
validate ───────┐
                ├─> build -> test-artifact -> publish-preflight
preconditions ──┘                                   │
                                       [approval]  approve-and-tag
                                                    │
                                       [approval]  publish -> verify-published -> github-release
```

1. **validate** — re-runs the entire `ci.yml` matrix, CodeQL included.
2. **preconditions** — `scripts/check_release_preconditions.py`: the run is a
   `workflow_dispatch` on `refs/heads/main`; the checkout is the current head
   of `main` on the remote; the version is a publishable v0.x version with no
   `v<version>` tag on the remote or in the checkout; the `pypi` environment
   has required reviewers and a deployment branch policy. Then
   `set_workspace_version.py release <version> --check`, `uv lock --check`,
   and offline publish readiness with `--oidc-identity`.
3. **build** — `uv build --all-packages` produces exactly fourteen files;
   validates the reviewed set, every artifact's metadata and contents, and
   offline publish readiness against the built set; records SHA-256 digests.
   Read-only permissions, no OIDC. **Build once, promote the same artifact.**
4. **test-artifact** — clean environment outside the workspace, third-party
   dependencies resolved first, then all seven wheels installed with the index
   closed; isolated origin/metadata/data checks, every import, every console
   script.
5. **publish-preflight** — preconditions again, then the public index: refuses
   if this version already has files anywhere in the set, or if a recorded
   publisher kind disagrees with whether its project exists.
6. **approve-and-tag** — waits in the `pypi` environment for a reviewer.
   Re-checks every precondition, creates the annotated `v<version>` tag on
   the dispatched commit as `github-actions[bot]`, pushes it and verifies it
   with `check_release_tag.py`. The only job that creates a tag; holds
   `contents: write` and nothing else.
7. **publish** — waits in the `pypi` environment again. `id-token: write` and
   `contents: read`. Checks out the tag, asserts it names the dispatched commit
   and reviewed `main` history, re-validates the downloaded bundle, stages each
   distribution separately, then uploads **siblings first and `agnara` last**,
   one reviewed step each, with metadata verification, attestations and hash
   printing. `skip-existing` is off.
8. **verify-published** — asserts every distribution is *complete* on the index
   (wheel and sdist), then installs the published set into a clean environment
   and exercises it.
9. **github-release** — depends on step 8. Creates the GitHub Release for the
   tag from step 6, from `docs/releases/v<version>.md`.

### Why the kernel goes last

Multi-project uploads are not atomic, so an order exists whether or not anyone
chooses it. An adapter pins its kernel exactly, so publishing `agnara` last
makes a partial publication fail **closed**: siblings without their kernel
resolve for nobody, and the `agnara` version an ordinary install sees does not
move. `0.1.0a4` published the kernel first and failed open.

### If a publication is still partial

Stop. Do not rerun the workflow for the same version, do not enable
`skip-existing`, do not move the tag, do not delete or overwrite a published
file.

1. Read `publish-preflight`'s output and the retained
   `agnara-distribution-hashes` artifact to establish exactly what exists.
2. Record the state in `docs/releases/publication.json` (`last_registry_failure`
   and `pypi_state`) and in the release note.
3. Fix the external cause.
4. Select the **next** version and publish the complete set.
5. Once the new version is verified complete, yank the orphaned files with a
   reason naming the superseding version.

There is deliberately no resumable rerun. A resumable path needs either
`skip-existing`, which hides the ordinary error, or a "start from distribution
N" input, which hides which distribution the run is actually publishing. ADR
0079 records both refusals.

## 5. Security and authorizations

- **Forks cannot publish.** The OIDC claim strictly enforces `Blandskron/agnara`,
  and `--oidc-identity` refuses inside the run if the repository or workflow
  reference differs from the recorded tuple.
- **Environment protection is required, not optional.** The `pypi` environment
  must have at least one required reviewer and a deployment branch policy that
  admits only `main` (or protected branches). `check_release_preconditions.py`
  reads both through the API and refuses the release while either is missing,
  because an unprotected environment approves every run instantly. Do not
  enable *prevent self-review* while the dispatching owner is the only
  reviewer, or no one could approve.
- **Tag immutability.** A tag ruleset for `v*` should block update and
  deletion. It must not restrict creation: the workflow creates the tag with
  the run's own token.
- **Action pinning.** Every third-party action on the publication path is
  pinned to a full commit SHA with the human version in a trailing comment.
  `.github/dependabot.yml` keeps them moving; the publisher action is excluded
  from the grouped update so it is reviewed alone.
- **Least privilege per job.** Only `publish` holds `id-token: write`, and it
  cannot write contents. Only `approve-and-tag` and `github-release` hold
  `contents: write`, and neither holds the OIDC token. No job edits
  `publication.json`.
- **Artifact immutability.** PyPI files cannot be replaced. A defect after
  publication is fixed by the next version, never by deleting or overwriting.
- **Retention.** The artifact bundle is kept for thirty days and its digests for
  ninety, because diagnosing a partial publication needs the exact bundle.

## 6. TestPyPI (optional)

TestPyPI is an entirely separate registry. Publishing there needs its own
pending Trusted Publishers, configured by the owner in the TestPyPI web
interface. Once they exist, an intermediate `publish-testpypi` job targeting a
`testpypi` environment can be added between `publish-preflight` and
`approve-and-tag`.
