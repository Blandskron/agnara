# Releasing Agnara to PyPI

Agnara follows a highly automated, secure release pipeline designed to prevent accidental or malicious publications.

The primary artifact published is the `agnara` distribution (which internally maps to the capability kernel logic).

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

The project owner has pre-configured the following external contract in PyPI:
- **Project**: `agnara`
- **Publisher**: GitHub
- **Repository**: `Blandskron/agnara`
- **Workflow**: `release.yml`
- **Environment**: `pypi`

## 3. How to Draft a Release

Publication is triggered by pushing the version tag; everything before that is
manual and reviewable.

ADR 0021 keeps every first-party package on one synchronized version, so a
release updates all seven, not only the published one.

1. Branch `release/v<version>` from `develop`.
2. Set the same version in **every** `packages/*/pyproject.toml` (e.g.
   `0.1.0a1`).
3. Run `uv lock` and confirm `uv lock --check` is clean.
4. Close `CHANGELOG.md`: rename `[Unreleased]` to `[<version>] - YYYY-MM-DD`,
   open a new empty `[Unreleased]`, and update the comparison links.
5. Build and validate the artifacts, then install the wheel into a clean
   environment outside the checkout and run the quick start.
6. Open the PR to `main`, wait for every required check, and merge through the
   mechanism branch protection allows.
7. Tag the exact merged commit, annotated:

```bash
git tag -a v0.1.0a1 -m "Agnara v0.1.0a1 — First Public Alpha"
git push origin v0.1.0a1
```

8. Propagate the release-only commits back to `develop` through a PR.

Only `agnara` is published. The adapter packages carry the synchronized
version and are buildable from the repository, but each additional
distribution needs its own PyPI Trusted Publisher before it can be uploaded.

## 4. The `release.yml` Workflow

Upon receiving the tag `v*.*.*`, `.github/workflows/release.yml` executes:

1. **Validation**: Re-runs the entire `ci.yml` matrix.
2. **Build**: Uses `uv build --package agnara` to generate the `sdist` and `wheel`. **Build Once, Promote Same Artifact.**
3. **Artifact Validation**: Downloads the wheel, creates a clean environment outside the workspace, installs it, and runs a minimal smoke test (`import agnara`). Ensures the tag version matches the package metadata exactly.
4. **Publish to PyPI**: The `publish` job runs in the `pypi` GitHub Environment. It uses OIDC (`id-token: write`) to securely assume the PyPI identity and upload the validated distributions.
5. **Post-release Verification**: Installs the newly published version directly from PyPI (after a brief delay for indexing) and verifies it imports correctly.
6. **GitHub Release**: Automatically drafts the official GitHub Release attached to the tag, generating release notes based on merged PRs, and attaches the binary artifacts.

## 5. Security & Authorizations

- **Forks cannot publish**: The OIDC claim strictly enforces `Blandskron/agnara`.
- **Environment Protections**: The `pypi` environment in GitHub can optionally be configured with required manual approvals.
- **Artifact Immutability**: If a release fails or has a bug post-publication, **do not delete or overwrite it**. Bump the version (e.g. `0.1.1`) and release anew.

## 6. TestPyPI (Optional but recommended)

TestPyPI is an entirely separate registry from PyPI. To publish to TestPyPI before production, a Pending Trusted Publisher must also be configured there. Configuring it is a repository-owner action in the TestPyPI web interface. Once a Pending Trusted Publisher exists there, an intermediate `publish-testpypi` job targeting a `testpypi` environment can be added before the `publish` job.

