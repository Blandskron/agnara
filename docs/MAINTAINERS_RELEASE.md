# Releasing Agnara to PyPI

Agnara follows a highly automated, secure release pipeline designed to prevent accidental or malicious publications.

The reviewed publication set is the seven synchronized first-party
distributions in ADR 0073. `agnara` is the kernel; HTTP, MCP, CLI and telemetry
are usable adapters, while A2A and events are explicitly reserved namespaces
with zero public names.

## 1. Quality Gates and Release Readiness

Before a release is drafted, the repository must pass all automated quality gates. You can verify readiness locally by ensuring that the framework is in a clean state:
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

When 100% green, the framework is technically ready to be packaged.

### Licensing Readiness Check
Before the first public release, verify:
- [x] LICENSE exists
- [x] Apache-2.0 selected
- [x] package metadata declares Apache-2.0
- [x] wheel contains required license metadata/files
- [x] sdist contains required license metadata/files
- [x] README license documentation is consistent
- [x] no contradictory "license pending" documentation remains

## 2. GitHub Actions and OIDC

Agnara uses **PyPI Trusted Publishing via OpenID Connect (OIDC)**. No passwords, tokens, or `.pypirc` files are ever stored in the repository or personal environments.

The project owner has pre-configured this external contract for `agnara`. Before
the first multi-package release, the identical Pending Trusted Publisher must
exist for `agnara-http`, `agnara-mcp`, `agnara-cli`, `agnara-telemetry`,
`agnara-a2a` and `agnara-events`:

- **Projects**: the seven names in ADR 0073
- **Publisher**: GitHub
- **Repository**: `Blandskron/agnara`
- **Workflow**: `release.yml`
- **Environment**: `pypi`

## 3. How to Draft a Release

Publication is triggered by pushing the version tag; everything before that is
manual and reviewable.

ADR 0021 keeps every first-party package on one synchronized version, so a
release updates all seven, not only the published one. ADR 0069 additionally
requires every adapter to pin that exact core version; these thirteen values
are changed only through the workspace transition tool.

1. Branch `release/v<version>` from `develop`.
2. Run `python scripts/set_workspace_version.py release <version>`. The command
   validates the complete workspace before writing, updates all project
   versions and adapter core pins, and refreshes `uv.lock` as one operation.
3. Run `python scripts/set_workspace_version.py release <version> --check`.
4. Close `CHANGELOG.md`: rename `[Unreleased]` to `[<version>] - YYYY-MM-DD`,
   open a new empty `[Unreleased]`, and update the comparison links.
5. Build all seven wheels and sdists. Run `scripts/check_distributions.py`
   against the artifact directory, then install adapter-owned third-party
   dependencies and all seven local wheels into a clean environment. Close
   index access for the first-party install and run the checker with `-I`.
6. Open the PR to `main`, wait for every required check, and merge through the
   mechanism branch protection allows.
7. Tag the exact merged commit, annotated:

```bash
git tag -a v0.1.0a1 -m "Agnara v0.1.0a1 — First Public Alpha"
git push origin v0.1.0a1
```

8. Propagate the release-only commits back to `develop` through a PR. Once the
   next `current_target` is selected, run
   `python scripts/set_workspace_version.py development <next-version>` so
   `develop` carries `<next-version>.dev0`.

Write `docs/releases/v<version>.md` before tagging. `release.yml` uses it as
the GitHub Release body and appends the generated PR list underneath, so a
missing file silently degrades the release notes to the generated list.

Today only `agnara` is published (`0.1.0a3`). The repository and workflow are
publication-ready for all seven at `0.1.0a4`; do not describe the six new PyPI
projects as published until the tagged workflow has uploaded and verified them.
Each additional name needs the Pending Trusted Publisher above before the tag
is pushed. No package-specific workflow edit is part of release preparation.

## 4. The `release.yml` Workflow

Upon receiving the tag `v*.*.*`, `.github/workflows/release.yml` executes:

1. **Validation**: Re-runs the entire `ci.yml` matrix.
2. **Build**: Uses `uv build --all-packages` to generate exactly fourteen files, then validates the explicit reviewed set and every artifact's metadata/content. **Build Once, Promote Same Artifact.**
3. **Artifact Validation**: Downloads those artifacts, creates a clean environment outside the workspace, installs all seven wheels without first-party index access, runs isolated origin/metadata/data checks, imports every package and exercises the `agnara` console script. The tag version must match every distribution.
4. **Publish to PyPI**: Only a pushed version tag enables this job. It runs in the `pypi` GitHub Environment, obtains OIDC (`id-token: write`) and uploads the exact validated files with metadata checks and attestations enabled. Manual dispatch never publishes.
5. **Post-release Verification**: Installs all seven synchronized distributions directly from PyPI (after a brief delay for indexing), imports them and exercises the console script.
6. **GitHub Release**: Automatically drafts the official GitHub Release attached to the tag, generating release notes based on merged PRs, and attaches the binary artifacts.

## 5. Security & Authorizations

- **Forks cannot publish**: The OIDC claim strictly enforces `Blandskron/agnara`.
- **Environment Protections**: The `pypi` environment in GitHub can optionally be configured with required manual approvals.
- **Artifact Immutability**: If a release fails or has a bug post-publication, **do not delete or overwrite it**. Bump the version (e.g. `0.1.1`) and release anew.

## 6. TestPyPI (Optional but recommended)

TestPyPI is an entirely separate registry from PyPI. To publish to TestPyPI before production, a Pending Trusted Publisher must also be configured there. Configuring it is a repository-owner action in the TestPyPI web interface. Once a Pending Trusted Publisher exists there, an intermediate `publish-testpypi` job targeting a `testpypi` environment can be added before the `publish` job.
