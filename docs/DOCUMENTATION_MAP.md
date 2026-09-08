# Documentation Map

Which document owns which kind of truth, and what every other document should
do instead of repeating it.

This exists because the same decision was being maintained in several files.
`ROADMAP.md`, `BACKLOG.md` and `docs/releases/RELEASE_PLAN.md` all described
future work in three different vocabularies, and nothing said which one was
right when they disagreed.

## The hierarchy

```text
VISION            why Agnara exists
   ↓
PRINCIPLES        the rules a decision must not break
   ↓
ARCHITECTURE      how the system is structured today
   ↓
RFC / ADR         individual decisions: open, then settled
   ↓
TARGET ARCH       where the structure is going
   ↓
INITIATIVES       what to build, in dependency order
   ↓
INTEROPERABILITY  how Agnara relates to the ecosystem it will not replace
   ↓
BACKLOG           decomposed items, close enough to implement
   ↓
RELEASE PLAN      what a given release must satisfy
```

Each level may cite the level above it. None should restate it.

## Ownership

| Truth | Owner | Everyone else |
| --- | --- | --- |
| Why the project exists | `VISION.md` | cite |
| Non-negotiable rules | `PRINCIPLES.md` | cite |
| Current structure, boundaries, dependency direction | `ARCHITECTURE.md` | cite |
| **What exists, per subsystem** | `docs/MATURITY.md` | cite; never restate a status |
| One settled decision | the ADR | cite by number |
| One open design question | the RFC | cite by number |
| Long-term structure and gaps | `docs/TARGET_ARCHITECTURE.md` | cite |
| **Interoperability contract and integration matrix** | `docs/INTEROPERABILITY.md` | cite; never restate a priority or a gate |
| What to build and in what order | `docs/INITIATIVES.md` | cite by initiative id |
| Decomposed, ready work | `BACKLOG.md` | cite by item id |
| Release gates and evidence | `docs/releases/RELEASE_PLAN.md` + `release-status.json` | cite |
| Current a4 closure sequencing | `docs/releases/A4_RELEASE_CLOSURE.md` | cite; it schedules work but does not satisfy a gate |
| What a release actually contained | `docs/releases/v*.md`, `CHANGELOG.md` | never edit retroactively |
| Quality gate definitions | `QUALITY_GATES.md` | cite |
| Performance method and results | `PERFORMANCE.md`, `docs/benchmarks/` | cite |
| Security posture and gaps | `SECURITY.md` | cite |
| What a `0.1.0a3` user must change | `docs/MIGRATION_a3_to_a4.md` | cite; never document an internal change as user migration work |
| CLI surface | `docs/CLI_SPEC.md` | cite |
| Generated project layout | `docs/SCAFFOLDING.md` | cite |
| Manifest format | `docs/PROJECT_MANIFEST.md` | cite |
| Public API shape and intent | `docs/API_DESIGN.md` | cite |
| How to serve capabilities over HTTP | `docs/HTTP_COMPOSITION.md` | cite; never restate a limitation |
| Public API inventory and stability policy | `docs/PUBLIC_API.md` + `docs/public-api.json` | cite |
| External standards studied | `docs/REFERENCE_RESEARCH.md` | cite |
| Contribution and git process | `CONTRIBUTING.md`, `GIT_WORKFLOW.md` | cite |
| Agent operating rules | `AGENTS.md` | cite |

## Rules

**A status is stated once.** If a subsystem's maturity appears in two files,
one of them is going to be wrong. `docs/MATURITY.md` is the one that is right.

**A roadmap does not contain a backlog.** `ROADMAP.md` states horizons and
points at initiatives. It does not list tasks.

**A matrix is not a gate.** `docs/INTEROPERABILITY.md` records which
integrations matter and in which direction. Which of them a release cannot
close without is `docs/releases/RELEASE_PLAN.md`, and the matrix points at it
rather than repeating it.

**An ADR records a decision that was made.** Not a speculation. Open questions
belong in an RFC until they are answered, and an RFC that has been answered
says so and names the ADR.

**Release history is immutable.** `docs/releases/v0.1.0a1.md` describes what
`0.1.0a1` was, including what was wrong with it. It is never corrected to
match a later reality.

**Prefer a citation to a copy.** A reader who follows a link to one accurate
paragraph is better served than one who reads four paragraphs that used to
agree.

## Automated checks

`tests/architecture/test_documentation_consistency.py` enforces the parts of
this that a machine can check:

- every package listed in `docs/MATURITY.md` exists, and vice versa;
- the public-name counts in the maturity table match the packages, and the
  exact top-level core exports match their stability manifest;
- every status token used is in the declared vocabulary;
- every canonical document this map names exists;
- every ADR and RFC referenced by the planning documents exists;
- no planning document references a file that has been deleted.

Everything else is a human judgement, and this file is where the judgement is
recorded so the next reader does not have to reconstruct it.
