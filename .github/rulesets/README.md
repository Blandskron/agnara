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
| `pull_request` | Direct pushes rejected; every change arrives through a PR |
| `required_status_checks` | The aggregate `CI` check must pass, on an up-to-date branch |
| `required_review_thread_resolution` | Open review conversations block merge |
| `non_fast_forward` | Force pushes rejected |
| `deletion` | The branch cannot be deleted |

## Human approval is a commitment, not an enforced control

`required_approving_review_count` is `0`, and that is deliberate rather than an
oversight. GitHub does not let a pull request author approve their own pull
request, so on a repository with one human maintainer a required approval is
not a stricter rule — it is a rule that can only be satisfied by having some
other account approve the maintainer's own work. That would manufacture the
review trail ADR 0092 exists to keep honest, which is worse than not enforcing
it. `docs/releases/1.0-release-rehearsal.md` section 7 reached the same
conclusion and this configuration follows it.

What is enforced instead is everything that does not require a second person:
no direct pushes, `CI` green, the branch up to date with its base
(`strict_required_status_checks_policy`), every review conversation resolved,
no force push, no deletion.

So the review half of `Issue → branch → PR → CI → review → approval → merge` is
a commitment the maintainer keeps, recorded in the PR's review trail, not a
control the platform applies. `GIT_WORKFLOW.md` says the same thing in the same
words, on purpose: the previous version of this file claimed one approval was
required while the workflow documentation described a rule nothing enforced,
and a governance document that overstates its own enforcement is worse than one
that admits the gap.

`dismiss_stale_reviews_on_push` and `require_last_push_approval` stay `true` in
these definitions. With no approval required they gate nothing today; they are
kept so that adding a second maintainer or a review bot is a one-line change to
`required_approving_review_count` rather than a redesign.

These JSON files are the reviewed source definitions. Applying them is a
maintainer action through Settings or the API — this repository change does not
silently mutate GitHub settings. `protect-release-tags` is applied and active;
the two branch definitions above are not yet applied, and the live rulesets
still carry the pre-review configuration.

## Why no bypass actors

`bypass_actors` is empty on purpose, so nobody silently pushes past the rules.

A repository admin can still edit or disable a ruleset in settings if a real
emergency demands it. That is a visible, auditable action, unlike a
per-push bypass that leaves no trace. It is the intended escape hatch.
