# ADR 0073 — Reviewed Distribution Publication Set

- Status: Proposed
- Date: 2026-09-07
- Tracking: GitHub Issue #291
- Release: `0.1.0a4`
- Amends: ADR 0021, ADR 0069

## Context

The workspace contains seven synchronized distributions. CI built all seven,
but the tag workflow built, installed and published only `agnara`. An external
application could therefore install the kernel but not its HTTP, MCP, CLI or
telemetry adapter as an ordinary dependency.

Changing the build command to `--all-packages` alone is unsafe. It makes a new
workspace directory part of the OIDC-authorized upload without a separate
reviewed decision. Building a wheel is also weaker evidence than installing it:
an adapter can resolve a public-index core instead of the candidate wheel, and
an import from the checkout can conceal a missing package file.

PyPI was queried on 2026-09-07. `agnara==0.1.0a3` is published; none of the six
sibling names has a PyPI project. The repository candidate version is
`0.1.0a4.dev0` for all seven distributions.

## Inventory and publication intent

| Distribution | Import | Core requirement | Other requirements | Script | Public names | PyPI now | Needed by a4 applications |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| `agnara` | `agnara` | — | — | — | 41 | `0.1.0a3` | yes |
| `agnara-http` | `agnara_http` | exact synchronized version | — | — | 7 | no project | yes |
| `agnara-mcp` | `agnara_mcp` | exact synchronized version | `mcp==2.1.1` | — | 20 | no project | where MCP evidence applies |
| `agnara-cli` | `agnara_cli` | exact synchronized version | — | `agnara` | 17 | no project | yes, for CLI/introspection evidence |
| `agnara-telemetry` | `agnara_telemetry` | exact synchronized version | `opentelemetry-api>=1.44,<2` | — | 2 | no project | where observability is exercised |
| `agnara-a2a` | `agnara_a2a` | exact synchronized version | — | — | 0 | no project | no; reserved namespace |
| `agnara-events` | `agnara_events` | exact synchronized version | — | — | 0 | no project | no; reserved namespace |

The reviewed publication set is all seven distributions. Publishing the two
reserved namespaces does not promote their maturity: their package READMEs and
`docs/MATURITY.md` state that they contain no public API or runtime. Keeping
them synchronized reserves the official package boundaries and avoids a later
package-set migration.

## Decision

1. `scripts/check_distributions.py` owns an explicit seven-name publication
   allowlist and fails if workspace discovery differs from it.
2. Every release build produces exactly one wheel and one sdist for each name.
   Before installation, the checker validates names, versions, Python floor,
   license metadata/files, README metadata/files, project URLs, classifiers,
   dependencies, console scripts, package data and safe archive paths. Direct,
   editable and Git requirements are refused.
3. Installed-artifact validation first resolves only the two adapter-owned
   third-party dependencies. It then installs all seven first-party wheels with
   `--no-index --find-links <candidate dist>`, and runs the checker through the
   environment's Python with `-I`. Every import must originate in
   `site-packages` outside the checkout.
4. The tag version must equal every source and installed distribution version.
5. The build job has read-only permissions and uploads only the fourteen
   checked distribution files. The OIDC publish job downloads that artifact;
   it does not rebuild.
6. Manual workflow dispatch may exercise validation but may not publish. Only
   a pushed `v*.*.*` tag can enter the PyPI environment and obtain
   `id-token: write`.
7. PyPI metadata verification, uploaded-artifact hash reporting and Trusted
   Publishing attestations are explicit. Third-party Actions in the release
   workflow use exact release tags.
8. Each of the seven PyPI projects must configure the same pending Trusted
   Publisher tuple — repository `Blandskron/agnara`, workflow `release.yml`,
   environment `pypi` — before the first multi-package tag is pushed. This is
   registry configuration, not package surgery.

## Threat analysis

### Accidental package publication

An attacker or mistaken change could add a workspace package and rely on
`--all-packages` plus a broad `dist/` upload. The explicit allowlist, exact
wheel/sdist count and surplus-artifact rejection stop before OIDC is available.

### Candidate core substitution

An adapter has an exact core pin, but an installer with index access could
still choose a published file of that version. Index access is closed for the
complete first-party installation, and all candidate wheels are supplied in
one transaction. Installed metadata is checked again afterward.

### Checkout masking

Running smoke tests from the repository can import `packages/*/src` even when a
wheel is absent or incomplete. Validation changes directory to an external
environment, uses isolated Python and rejects both non-`site-packages` origins
and paths under the checkout.

### Privilege and artifact mutation

Build scripts do not receive an OIDC token. Publication downloads the artifact
already validated by the preceding job and does not run package build code.
Only the publish job has `id-token: write`; tag-only gating prevents an
operator from turning an arbitrary manual dispatch into a release.

### Archive content and dependency confusion

The checker rejects traversal/absolute archive members, cache/test/experiment
trees, common credential filenames and token/private-key signatures outside
the separately hash- and license-verified vendored asset tree, direct URLs and
Git dependencies. Exact
first-party pins and a closed-index candidate install address dependency
confusion within the Agnara set. This is not a general secret scanner or SBOM;
those remain separately `PLANNED` in `docs/MATURITY.md`.

## Consequences

- A release tag can publish the intended set without editing the workflow or
  moving artifacts by hand.
- The first multi-package upload still depends on the owner configuring six
  new pending Trusted Publishers in PyPI. The workflow cannot and should not
  create that external trust relationship.
- `agnara-a2a` and `agnara-events` become installable reserved packages, not
  implemented adapters. Their zero-name public surfaces remain governed.
- Adding or removing a first-party distribution now requires an explicit ADR,
  allowlist change, inventory update and release-workflow review.
