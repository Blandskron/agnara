# Branch and tag rulesets

The JSON files here are the rulesets applied to `main`, `develop` and the
`v*` release tags. They are version controlled so the enforced configuration
is reviewable in the repository rather than only visible in GitHub settings.

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
| `pull_request` | Direct pushes rejected; every change arrives through a PR |
| `required_status_checks` | The aggregate `CI` check must pass before merge |
| `required_review_thread_resolution` | Open review conversations block merge |
| `non_fast_forward` | Force pushes rejected |
| `deletion` | The branch cannot be deleted |

## Why zero required approvals

`required_approving_review_count` is deliberately `0`.

GitHub does not permit a pull request author to approve their own pull
request. While Agnara has a single agent identity, any non-zero value would
make the repository impossible to merge into, which `GIT_WORKFLOW.md`
forbids and ADR 0016 addresses directly: the repository must represent the
real strength of its review process rather than fabricate one.

Raise this to `1` when a second independent identity exists — see `BACKLOG.md`
E0B.9. That is the single change needed to move from Mode B to Mode A.

## Why no bypass actors

`bypass_actors` is empty on purpose, so nobody silently pushes past the rules.

A repository admin can still edit or disable a ruleset in settings if a real
emergency demands it. That is a visible, auditable action, unlike a
per-push bypass that leaves no trace. It is the intended escape hatch.
