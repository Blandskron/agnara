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

## Two known blockers

Both are architectural, both are recorded, and neither is a defect introduced
since `0.1.0a3`:

1. **Only `agnara` is published.** The six sibling distributions are versioned
   and buildable but not uploaded, so an application that needs HTTP or MCP
   cannot install an adapter as an ordinary dependency. This blocks
   `reference-apps-exist` and `mcp-exposure-from-application`.
2. **`agnara-http` declares no public composition surface.** Composing HTTP
   requires importing underscore-prefixed modules, which is exactly what
   `reference-apps-no-internal-imports` forbids.

   The architectural half of this blocker is now resolved: the unified
   exposure model is implemented and RFC 0006 is answered by ADR 0070, so the
   model a composition API would sit on is settled and both adapters compile
   through it. **The blocker itself is unchanged.** `agnara-http` still
   exports nothing, an application still cannot compose HTTP through
   supported entry points, and this gate and `http-exposure-from-application`
   remain unsatisfiable. What changed is that the remaining work is an API on
   a decided model rather than a design question. `BACKLOG.md` E1C.3 owns it.

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
3. The two blockers above are resolved or explicitly deferred with a recorded
   decision.
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
