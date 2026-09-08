# Releasing Agnara to PyPI

Agnara follows a highly automated, secure release pipeline designed to prevent
accidental or malicious publications.

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

## 0. CODE READY is not PUBLISH READY

These are two different claims, they fail for different reasons, and conflating
them is how `0.1.0a4` published one of fourteen artifacts. Read
[ADR 0079](adr/0079-sequenced-publication-and-publish-readiness.md) before
running a release.

| Claim | Owner | Question |
| --- | --- | --- |
| CODE READY | `scripts/check_release_readiness.py` | Is the implementation mature enough to close this release? |
| PUBLISH READY | `scripts/check_publication_readiness.py` | Can this exact commit become seven complete distributions on the index? |

```bash
uv run python scripts/check_release_readiness.py --verbose
uv run python scripts/check_publication_readiness.py --version <version>
uv run python scripts/check_publication_readiness.py --version <version> --online
```

The `--online` form reads the public index. Before publishing it refuses if any
project already carries a file at that version; after publishing,
`--require-published` requires every project to carry both a wheel and an sdist.

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

When 100% green, the framework is **CODE READY**. That is half the answer.

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
| Provider | GitHub |
| Owner | `Blandskron` |
| Repository | `agnara` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

A project that does not exist yet needs a **pending** publisher, added at
<https://pypi.org/manage/account/publishing/>; it creates the project on first
upload and does not reserve the name. A project that already exists carries an
active publisher in its own Publishing settings.

**Verify by reading the four fields back, per project.** A 404 on the project
page proves nothing about whether a pending publisher exists, and PyPI answers
a name mismatch with `400 Non-user identities cannot create new projects` —
after it has already accepted the files before it in the batch.

Record each confirmation in [`docs/releases/publication.json`](releases/publication.json)
against the exact target version. `check_publication_readiness.py` fails while
any project is `UNVERIFIED`, and `release.yml` runs it before the first upload,
so an unconfirmed publisher stops the release rather than the release finding
out mid-upload.

If a project was created under a misspelled name, the fix is on PyPI: delete the
wrong project, remove the wrong publisher, re-register under the exact canonical
name. Never rename a distribution here to match a registry typo. `_` in a wheel
or sdist filename is PEP 427/625 normalization of the dash and is correct.

## 3. How to draft a release

Publication is triggered by pushing the version tag; everything before that is
manual and reviewable.

ADR 0021 keeps every first-party package on one synchronized version, so a
release updates all seven, not only the published one. ADR 0069 additionally
requires every adapter to pin that exact core version; these thirteen values are
changed only through the workspace transition tool.

1. Branch `release/v<version>` from `develop`.
2. `python scripts/set_workspace_version.py release <version>` — validates the
   complete workspace before writing, updates all project versions and adapter
   core pins, and refreshes `uv.lock` as one operation.
3. `python scripts/set_workspace_version.py release <version> --check`.
4. Close `CHANGELOG.md`: rename `[Unreleased]` to `[<version>] - YYYY-MM-DD`,
   open a new empty `[Unreleased]`, and update the comparison links.
5. Write `docs/releases/v<version>.md`. This is the GitHub Release body; the
   generated PR list is appended under it. It is no longer possible for a
   missing file to degrade the notes silently — publish readiness fails on it.
6. Set `docs/releases/publication.json` to this target and record the publisher
   confirmations from section 2.
7. Build all seven wheels and sdists, run `scripts/check_distributions.py`
   against the artifact directory, then install adapter-owned third-party
   dependencies and all seven local wheels into a clean environment with index
   access closed, and run the checker with `-I`.
8. `scripts/check_publication_readiness.py --version <version> --dist dist/`,
   then the `--online` form.
9. Open the PR to `main`, wait for every required check, and merge through the
   mechanism branch protection allows.
10. Tag the exact merged commit, annotated:

```bash
git tag -a v0.1.0a5 -m "Agnara v0.1.0a5 — Publication Recovery"
git push origin v0.1.0a5
```

11. Propagate the release-only commits back to `develop` through a PR. Once the
    next `current_target` is selected, run
    `python scripts/set_workspace_version.py development <next-version>` so
    `develop` carries `<next-version>.dev0`. **`0.1.0a4` skipped this step**, so
    `develop` sat at an exact release version instead of a development one.

## 4. The `release.yml` pipeline

Seven jobs, chained by real `needs`, so a failure at any point stops everything
after it:

```text
validate → build → test-artifact → publish-preflight
        → publish → verify-published → github-release
```

1. **validate** — re-runs the entire `ci.yml` matrix.
2. **build** — `uv build --all-packages` produces exactly fourteen files;
   validates the reviewed set, every artifact's metadata and contents, the tag,
   and offline publish readiness; records SHA-256 digests. Read-only
   permissions, no OIDC. **Build once, promote the same artifact.**
3. **test-artifact** — clean environment outside the workspace, third-party
   dependencies resolved first, then all seven wheels installed with the index
   closed; isolated origin/metadata/data checks, every import, every console
   script.
4. **publish-preflight** — reads the public index before any credential exists.
   Refuses if this version already has files anywhere in the set; reports which
   projects a pending publisher still has to create.
5. **publish** — only a pushed version tag reaches it. Runs in the `pypi`
   environment with `id-token: write` and no `contents: write`. Re-validates the
   downloaded bundle, stages each distribution separately, then uploads
   **siblings first and `agnara` last**, one reviewed step each, with metadata
   verification, attestations and hash printing. `skip-existing` is off.
6. **verify-published** — asserts every distribution is *complete* on the index
   (wheel and sdist), then installs the published set into a clean environment
   and exercises it.
7. **github-release** — depends on step 6. The only job with `contents: write`.

Manual dispatch never publishes: only a pushed `v*.*.*` tag enters the `pypi`
environment.

### Why the kernel goes last

Multi-project uploads are not atomic, so an order exists whether or not anyone
chooses it. An adapter pins its kernel exactly, so publishing `agnara` last
makes a partial publication fail **closed**: siblings without their kernel
resolve for nobody, and the `agnara` version an ordinary install sees does not
move. `0.1.0a4` published the kernel first and failed open.

### If a publication is still partial

Stop. Do not rerun the tag, do not enable `skip-existing`, do not move the tag,
do not delete or overwrite a published file.

1. Read `publish-preflight`'s output and the retained
   `agnara-distribution-hashes` artifact to establish exactly what exists.
2. Record the state in `docs/releases/publication.json` and in the release note.
3. Fix the external cause.
4. Select the **next** version and publish the complete set. This is what
   `0.1.0a5` is.
5. Once the new version is verified complete, yank the orphaned files with a
   reason naming the superseding version.

There is deliberately no resumable rerun. A resumable path needs either
`skip-existing`, which hides the ordinary error, or a "start from distribution
N" dispatch input, which would give a dispatch-triggered run the ability to
publish. ADR 0079 records both refusals.

## 5. Security and authorizations

- **Forks cannot publish.** The OIDC claim strictly enforces `Blandskron/agnara`.
- **Environment protections.** The `pypi` environment can require reviewers.
  Choosing its policy is an owner decision and is currently unset.
- **Action pinning.** Every third-party action on the publication path is
  pinned to a full commit SHA with the human version in a trailing comment.
  `.github/dependabot.yml` keeps them moving; the publisher action is excluded
  from the grouped update so it is reviewed alone.
- **Artifact immutability.** PyPI files cannot be replaced. A defect after
  publication is fixed by the next version, never by deleting or overwriting.
- **Retention.** The artifact bundle is kept for thirty days and its digests for
  ninety, because diagnosing a partial publication needs the exact bundle.

## 6. TestPyPI (optional)

TestPyPI is an entirely separate registry. Publishing there needs its own
pending Trusted Publishers, configured by the owner in the TestPyPI web
interface. Once they exist, an intermediate `publish-testpypi` job targeting a
`testpypi` environment can be added before `publish`.
