# Release Status

Current target: **0.1.0a4 — Application Alpha**.
Previous published release: **0.1.0a3**, published 2026-09-06 and verified on
PyPI.

Assessed 2026-09-07 against `develop`.

The readiness program reports **IN_PROGRESS**. `0.1.0a4` is **not** ready, and
most of its gates cannot produce evidence yet. That is the expected state, not
a regression: `0.1.0a4` is the release that asks whether Agnara can be consumed
from outside this repository, and the applications that answer it are still
being built.

## What `0.1.0a4` has to prove

That Agnara can be consumed as a framework rather than exercised internally.
Its evidence comes from applications outside this workspace — currently being
built in `agnara-project` — and those applications will be audited separately
before any gate here is recorded as satisfied.

Dogfooding the new HTTP composition API found and resolved its first framework
defect: JSON objects bound to standard-library dataclasses are now materialized
at the HTTP boundary and then validated by the unchanged strict core schema
path (ADR 0075, Issue #296). The public example exercises that path directly.

Nothing in this repository can satisfy the external gates on its own. Passing
repository tests is not evidence that an external consumer can do the same
thing, and the program is designed so that it cannot be mistaken for it.

## The path changed shape

`0.1.0a5` now sits between `0.1.0a4` and `0.1.0b1`, and `0.1.0b1` is the
interoperability and composition beta. ADR 0068 records the decision and
`RELEASE_PLAN.md` carries the gates.

Nothing about `0.1.0a4` moved. Its gates, its blockers and its score are
unchanged; the work that had no release — streaming, execution identity,
performance budgets, and framework interoperability — now has one each. The
practical effect on this release is a guardrail rather than a task: `0.1.0a4`
may not answer its "public APIs are sufficient" gate by shipping a framework
integration that routes around the API the gate is asking about.

## Publication state and known blockers

One public-index blocker remains. The repository-side packaging defect is
resolved, but this task deliberately did not publish anything:

1. **Only `agnara` is published.** The six sibling distributions are still not
   uploaded, so an application using only PyPI cannot install HTTP or MCP yet.
   All seven are now publication-ready: the tag workflow builds and validates
   the explicit fourteen-file set, installs every wheel with first-party index
   access disabled, and will publish those same files with Trusted Publishing
   attestations (ADR 0073). The six new PyPI names need Pending Trusted
   Publishers before the authorized release tag is pushed.
2. **~~`agnara-http` declares no public composition surface.~~ Resolved.**
   `agnara-http` exports seven `provisional` names that compose exposures,
   compile an ASGI 3 application and project OpenAPI (ADR 0071), on the
   exposure model ADR 0070 settled. `docs/HTTP_COMPOSITION.md` is the guide,
   and an architecture test fails if any example or guide reaches into a
   private module.

## Gate state

Run the checker for the current per-gate detail:

```bash
uv run python scripts/check_release_readiness.py --verbose
```

| Group | State |
| --- | --- |
| `0.1.0a3` automated gates | re-derived every run; satisfied on a clean tree |
| `0.1.0a3` evidence gates | reset — must be re-established against a `0.1.0a4` candidate commit |
| `0.1.0a3` manual gates | reset to review — the `0.1.0a3` decisions covered `0.1.0a3` |
| `0.1.0a4` evidence gates | unsatisfied, pending the external applications |
| `0.1.0a4` manual gates | pending maintainer judgment after the audit |

`RELEASE_PLAN.md` states the first `0.1.0a4` gate as a single automated gate,
"Every `0.1.0a3` gate still satisfied". It is decomposed into the individual
`0.1.0a3` gates in `release-status.json`, because the checker requires every
automated gate to have a real implementation and an aggregate gate over its
siblings would be circular. The decomposition also reports *which* part is
unsatisfied instead of one opaque failure.

## Where the `0.1.0a3` evidence went

It is preserved in [`history/0.1.0a3.md`](history/0.1.0a3.md), the maturity
snapshot `RELEASE_PLAN.md` requires after publication. That file records what
`0.1.0a3` proved, on what evidence, what it did not prove, and the limitations
it carried forward.

It is deliberately not carried into this file as satisfied. Evidence describes
the commit it was produced on; `0.1.0a3`'s evidence describes `0.1.0a3`.

## Remaining actions before `0.1.0a4` can be assessed

1. The reference applications in `agnara-project` are completed.
2. Those applications are audited against the `0.1.0a4` gates, and every
   framework deficiency they surface is filed as an Issue rather than worked
   around inside the application.
3. The six Pending Trusted Publishers are configured and the authorized a4
   release publishes the already publication-ready set. The former
   repository-side workflow blocker is resolved (ADR 0073); blocker 2 is
   resolved (ADR 0071).
4. The `0.1.0a3` evidence gates are re-established against a `0.1.0a4`
   candidate commit.

Only then does a readiness assessment mean anything. Until then this file
records an honest low score rather than an encouraging one.

## Reproduce

```bash
uv run python scripts/check_release_readiness.py --verbose
```

Add `--require-ready` to exit non-zero unless the target is `RELEASE_READY`;
it currently exits non-zero, which is correct.

Evidence expires when a covered path changes from its recorded commit to HEAD.
Records without coverage expire on any commit. Automated checks inspect the
repository; manual decisions retain their human evidence.
