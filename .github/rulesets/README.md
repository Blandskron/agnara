# Branch and tag rulesets

The JSON files here are the reviewed source definitions for `main`, `develop`
and `v*` release tags. They are version controlled so the intended enforced
configuration is reviewable in the repository rather than only visible in
GitHub settings. ADR 0092 found no active GitHub rulesets; Blandskron imports
or updates these definitions after approving the governance PR.

`protect-release-tags.json` makes every `v*` tag immutable: it blocks update,
force-update and deletion. It deliberately does **not** restrict creation. The
release workflow creates the tag with the run's own `GITHUB_TOKEN` after every
gate has passed, a reviewer has approved the run and PyPI has confirmed the
publication complete (ADR 0082); a creation
rule would block that token without a bypass it cannot hold, and nothing else
in the repository creates release tags any more.

## Applying

They can be imported through **Settings → Rules → Rulesets → New ruleset →
Import a ruleset**, or with the API:

```bash
gh api --method POST repos/OWNER/REPO/rulesets \
  --input .github/rulesets/protect-develop.json
```

To update an existing ruleset, `PUT` to
`repos/OWNER/REPO/rulesets/<ruleset-id>` with the same payload.

## What they enforce

Release tags (`protect-release-tags`):

| Rule | Effect |
|---|---|
| `update` | A `v*` tag, once created, cannot be moved |
| `non_fast_forward` | A `v*` tag cannot be force-updated |
| `deletion` | A `v*` tag cannot be deleted |

Both branches, identically:

| Rule | Effect |
|---|---|
| `pull_request` | Direct pushes rejected; every change arrives through a PR with one approval |
| `required_status_checks` | The aggregate `CI` check must pass before merge |
| `required_review_thread_resolution` | Open review conversations block merge |
| `non_fast_forward` | Force pushes rejected |
| `deletion` | The branch cannot be deleted |

## Human approval required

`required_approving_review_count` is `1`, stale reviews are dismissed after a
push, and the most recent push requires approval. ADR 0092 requires
agent-authored PRs to request that formal review from `Blandskron`; GitHub
rulesets cannot select an individual reviewer, so the request and review trail
make that accountability explicit. A PR author cannot satisfy the approval.

These JSON files are the reviewed source definitions. The current GitHub
repository returned no active rulesets during the ADR 0092 audit, so a
maintainer must import or update these definitions through Settings or the API
after approving the governance PR. This repository change does not silently
mutate GitHub settings.

## Why no bypass actors

`bypass_actors` is empty on purpose, so nobody silently pushes past the rules.

A repository admin can still edit or disable a ruleset in settings if a real
emergency demands it. That is a visible, auditable action, unlike a
per-push bypass that leaves no trace. It is the intended escape hatch.
