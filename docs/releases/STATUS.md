# Release Status

Current target: **0.1.0a3 — Integration Alpha**.
Previous published release: **0.1.0a2**.

Assessed 2026-09-06 against preparation commit
`647280a6f09feee591d312d993f59550ed68b90b`, from validated develop
`3128172baab60383c506ac2b5f3b43fdb29a77bd`.

The readiness program reports **RELEASE_READY**: every mandatory maturity gate
has evidence. This is not publication authorization. Final release PR CI,
review and explicit owner authorization remain separate release gates.

## Evidence

| Gate | Actual preparation evidence |
| --- | --- |
| Tests | `uv run pytest`: 2059 passed, 31 browser-only skipped; final release/architecture suite: 225 passed |
| Browser conformance | Both documented browser suites with `AGNARA_RUN_BROWSER_TESTS=1`: 31 passed |
| Lint / format / types | Ruff check and format check, ty check: passed |
| Versions / lockfile | Seven distributions at `0.1.0a3`; `uv lock` regenerated only their seven version records; `uv lock --check` passed |
| Builds / metadata | `uv build --all-packages --out-dir dist/release-a3`: seven wheels and seven sdists; Apache-2.0, license files, Python >=3.14 verified |
| Clean installation | External CPython 3.14.4 venv, explicit interpreter with `-I`; core quickstart success/failure paths passed before installing adapters; every installed first-party module resolves from site-packages |
| CLI | Checkout and installed CLI version/help passed; CLI suite passed within full tests |
| HTTP / MCP / architecture | Passed within full tests; bounded MCP official SDK conformance only |
| Changelog | Dated 0.1.0a3 section, empty Unreleased, exact previous/target comparison links |
| Documentation | Maintainer approved prepared public docs and notes on 2026-09-06 |
| Security scope | Maintainer confirmed experimental alpha on 2026-09-06; private reporting enabled and verified; security boundary and browser tests passed |

Artifact names and SHA-256 values are recorded in `release-status.json`.
They identify local validation artifacts, not future OIDC-published artifacts.
Source CI evidence:
[develop CI](https://github.com/Blandskron/agnara/actions/runs/33999688686).
Release tracking and recorded maintainer decisions:
[Issue #237](https://github.com/Blandskron/agnara/issues/237).

## Remaining release actions

1. Required release PR CI and documented complete-diff review.
2. Explicit owner authorization to close `v0.1.0a3`.
3. Merge to main, annotated immutable tag on the accepted commit, existing
   Trusted Publishing workflow and external PyPI verification.
4. Propagate release metadata to develop through a PR, then clean up the
   release branch. Write the maturity history snapshot only after publication.

## Known non-blocking alpha limitations

Only `agnara` is authorized for PyPI publication. The other six distributions
are versioned and buildable but are not uploaded. Threat modeling, dependency
audit, secret scanning and dedicated security static analysis remain pending
under the maintainer-confirmed experimental-alpha scope. No production,
general security, complete protocol conformance or new performance claim is
made. See `v0.1.0a3.md` for migration and adapter limitations.

The target remains `0.1.0a3` until publication is externally verified and the
owner confirms transition. No work toward the next release is started.

## Reproduce

```bash
uv run python scripts/check_release_readiness.py --verbose --require-ready
```

Evidence expires when a covered path changes from its recorded commit to HEAD.
Records without coverage expire on any commit. Automated checks inspect the
repository; manual decisions retain their human evidence. The evidence-only
commit following preparation does not change the validated packages or tests.
