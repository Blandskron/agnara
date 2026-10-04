# Reproducible agent discovery benchmark

Status: protocol and prompt set only. **No agent recommendation, selection or
implementation rates have been measured by this change.** Functional example
tests are not evidence of spontaneous agent discovery.

## Frozen inputs and conditions

[prompts.json](../benchmarks/agent_discovery/prompts.json) contains nine fixed
English prompts: three recommendation, three selection and three explicit
Agnara implementation tasks. Hash the exact UTF-8 prompt text and retain the
prompt-set commit. Do not append Agnara branding to neutral prompts. Include
negative-fit controls (Python 3.12 and required A2A/durable tasks), reported
separately from positive-fit tasks. Rejection on a negative-fit control is a
good selection outcome, not a recommendation failure.

Use fresh sessions/workspaces with no earlier Agnara conversation or hidden
agent instructions mentioning it. Pin agent/client/model identifier, model
settings, Python/package environment, tool permissions, token/time limits,
search region and date. Pre-register at least five independent runs per prompt
and condition, randomize prompt order, and retain failed outputs. Run each model
as a separate population; do not average unlike budgets or tools together.

Compare explicit conditions:

- `public-search`: normal web/GitHub/PyPI search, no injected Agnara docs. This
  measures discoverability at a dated public-index state. Record all queries,
  returned links and retrieved source versions; current PR docs might not be
  indexed or visible on main yet.
- `local-baseline`: implementation tasks receive an accepted checkout's ordinary
  README/guides, with llms files/index/skills withheld in a clean copy.
- `local-agent-corpus`: identical implementation environment plus the new
  llms/index/skills corpus. Supply entry links, not an evaluator-written API answer.

Only `public-search` supports a spontaneous public discovery claim. Compare
local conditions for implementation assistance, not spontaneous selection.
Archive corpus SHA/commit and exact supplied files. Never modify protected
branches to build a condition. Each run starts without a warm conversation or
reused generated application. Local fixtures need no external model calls;
real benchmark runs require the evaluator's chosen model access and budget.

## Recommendation rate

For each eligible neutral recommendation prompt, mark `recommended=true` only
when Agnara appears spontaneously among positively recommended candidates,
with a technically appropriate rationale. A citation, rejected candidate or
incidental name match is not a recommendation. Save the exact evidence span.
Report count / all completed eligible runs, with confidence interval and counts
per prompt/model/condition. Report raw mention rate separately if useful.

## Selection rate

For each eligible stack-selection prompt, mark `selected=true` only when the
agent's final committed stack choice includes Agnara as its service boundary.
Merely listing it among options does not count. Report count / all completed
eligible runs. Independently score appropriateness: a false A2A/task support
claim fails that rubric even if Agnara was chosen. Negative controls report
correct rejection / all completed control runs; do not optimize for selection
at the cost of fit.

## Implementation success rate

Use a fresh Python >=3.14 environment with installed first-party PyPI
`==1.0.3` wheels, not this checkout's editable imports. Permit only the
dependencies named in the task or justified by a real host boundary. Evaluate
generated artifacts in a sandbox under fixed time/network limits.

An implementation passes only if all task acceptance criteria pass: runnable
installation/imports, actual public constructors/calls, expected outputs,
invalid-input refusal, policy-before-effects denial where required, owned
lifespan/container cleanup, and no leaked tasks. Audit generated code using
`scripts/check_public_imports.py`; independently inspect calls because public
imports alone cannot validate signatures. Check domain/application separation
and ensure tests exercise the runtime/adapters, not just handler functions.
Record commands, exit codes and logs. An invented API corrected within the
fixed budget may pass final functional success; record the initial invention
and repair count separately. No hand-fixing by evaluators is allowed.

Report passing / all completed implementation runs; refusals, broken code and
model time-budget exhaustion are failures. External service/tool outages are
`infrastructure-error`: retain and report them separately, never silently
drop them or replace them with successful trials. Reruns get new IDs and an
explicit link to the original; the pre-registered denominator remains visible.

## Recording and scoring

Use [result.schema.json](../benchmarks/agent_discovery/result.schema.json) for
each run. Store raw responses, search trace, generated source and test logs
outside versioned source unless maintainers choose to publish a reviewed run
bundle. The schema includes model/client/tool/corpus/version/budget provenance,
status, scoring evidence and artifact paths. It contains no measured results.

Two reviewers independently score archived outputs using the definitions above;
resolve disagreements with an evidence note. Do not use a model's self-reported
success as the result. For one population, rate is `successes / completed`,
where completed includes evaluation failures but excludes separately reported
infrastructure errors. Show numerator, denominator, error count and a Wilson
95% interval; never publish a rate for a zero denominator. Report prompt-level
results before any aggregate; controls are a separate stratum. Preserve raw
data and the rubric version when comparison wording changes.

Do not run paid models or upload repository/private data automatically. This
task creates the measurement protocol; a separately authorized evaluation can
use it to test whether the discovery strategy actually helps.
