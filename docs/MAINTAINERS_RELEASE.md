# Releasing Agnara to PyPI

Agnara follows a highly automated, secure release pipeline designed to prevent accidental or malicious publications.

The primary artifact published is the `agnara` distribution (which internally maps to the capability kernel logic).

## 1. Quality Gates and Release Readiness

Before a release is drafted, the repository must pass all automated quality gates. You can verify readiness locally by ensuring that the framework is in a clean state:
```bash
uv pip install -e ".[dev]"
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

When 100% green, the framework is technically ready to be packaged.

## 2. GitHub Actions and OIDC

Agnara uses **PyPI Trusted Publishing via OpenID Connect (OIDC)**. No passwords, tokens, or `.pypirc` files are ever stored in the repository or personal environments.

The project owner has pre-configured the following external contract in PyPI:
- **Project**: `agnara`
- **Publisher**: GitHub
- **Repository**: `Blandskron/agnara`
- **Workflow**: `release.yml`
- **Environment**: `pypi`

## 3. How to Draft a Release

The pipeline is triggered automatically when a new version tag is pushed:

1. Update the version in `packages/agnara/pyproject.toml` (e.g. to `0.1.0`).
2. Run `uv lock` to update the lockfile workspace metadata.
3. Commit and merge to `main` via PR.
4. Draft a new tag `v0.1.0`.

```bash
git tag v0.1.0
git push origin v0.1.0
```

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

TestPyPI is an entirely separate registry from PyPI. To publish to TestPyPI before production, a Pending Trusted Publisher must also be configured there. See **ACTION REQUIRED FROM OWNER** in the AI agent prompt output for instructions on configuring TestPyPI. Once configured, an intermediate job `publish-testpypi` targeting the `testpypi` environment can be added before the `publish` job.
