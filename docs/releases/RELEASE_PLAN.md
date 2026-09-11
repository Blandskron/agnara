# Agnara Release Plan

## Baseline and target

`0.1.0a8` is the sole retained publication baseline. It proved the reviewed,
dispatch-driven seven-distribution publication path; it is not the compatibility
or product contract this project will publish next.

<<<<<<< HEAD
```text
0.1.0a2     (published 2026-09-04)
   ↓
0.1.0a3     subsystem integration      (published 2026-09-06)
   ↓
0.1.0a4     external application validation    (tagged 2026-09-08;
   ↓                                            published partially)
0.1.0a5     publication recovery              (aborted before upload)
   ↓
0.1.0a6     publication recovery              (aborted on first upload)
   ↓
0.1.0a7     publication and security recovery (aborted before upload)
   ↓
0.1.0a8     release pipeline recovery         ← current target
   ↓
0.1.0a9     execution semantics and cost
   ↓
0.1.0b1     interoperability and composition
   ↓
0.1.0rc1    stability candidate
   ↓
0.1.0       first stable contract
```
=======
The next and first planned product release is **`1.0.0`**. There will be no
additional interim publication cadence. Development
continues on `develop` until the stable gates below have evidence.
>>>>>>> 15cdde3ccb0211665dc88e153872be1acdeee5aa

## Release thesis

`1.0.0` proves that Agnara's capability runtime and its documented public
surface are stable enough for production adoption. It must not be cut merely
because a subsystem milestone is complete.

<<<<<<< HEAD
| Release | Question | Owns |
| --- | --- | --- |
| `0.1.0a4` | Can Agnara be consumed as a framework from outside this repository? | I1, I7, the public exposure and composition surface |
| `0.1.0a5` | Did publication readiness stop an unsafe release attempt before upload? | the first enforced preflight; aborted because publisher confirmation was absent |
| `0.1.0a6` | Can Agnara publish the set it builds, completely, and prove that it did? | aborted on the first upload; no artifact published |
| `0.1.0a7` | Can corrected publisher evidence and release security publish the complete set? | aborted before upload: tagged while the publication record was `UNVERIFIED` |
| `0.1.0a8` | Can a release no longer consume a version before every gate and a human have said yes? | the dispatch-driven release flow, ADR 0082, with the A7 runtime unchanged |
| `0.1.0a9` | Does execution have streaming, identity and a measured cost? | I2, I3, I14 |
| `0.1.0b1` | Can the Python ecosystem use Agnara, and Agnara use it? | I20, and the beta contract gates |

No alpha may declare stable support for an external framework;
`EXPERIMENTAL` is the strongest status any of them may give an integration.
=======
The work leading to it includes streaming semantics, execution identity and
operational idempotency; performance budgets enforced in CI; interoperability
and composition evidence; security-program evidence; a stable public API; and
repeatable publication of all seven distributions.

## Gates
>>>>>>> 15cdde3ccb0211665dc88e153872be1acdeee5aa

All existing quality, security, packaging and review requirements remain in
force. The `1.0.0` release additionally requires evidence for each item below.

| Gate | Evidence |
| --- | --- |
| Execution semantics | Streaming, identity and idempotency have accepted designs, implementations and conformance tests. |
| Performance | Budgets cover compiled execution paths and regressions fail CI. |
| Interoperability | Standalone, hosted, embedded and side-by-side scenarios satisfy the approved contract. |
| Security | Threat model, dependency/supply-chain checks and security invariants have current evidence. |
| Public API | Every public export is classified stable or deprecated with migration guidance. |
| Documentation | A clean-room application can be built from supported documentation alone. |
| Publication | The A8 workflow builds, verifies and publishes all distributions from the accepted `1.0.0` commit. |

<<<<<<< HEAD
One file convention, and one place the evidence lives:

- `docs/releases/v<version>.md` — the **user-facing release note**, written
  for whoever installs the package. The working tree keeps the release being
  prepared and, while it still helps an upgrader, the one before it.
- `docs/releases/release-status.json` — the **evidence record** for the
  current target: which gate was satisfied, by what command, at which commit.

What a published release proved is answered by its tag, its GitHub Release
and the `release-status.json` at that tag, so no separate in-tree maturity
snapshot is maintained. `docs/DOCUMENTATION_MAP.md` states the rule.

## Gate kinds

Every gate is one of three kinds, and the distinction is enforced by
`scripts/check_release_readiness.py`:

| Kind | Meaning | Who decides |
| --- | --- | --- |
| **automated** | Re-derived from the repository on every run | The checker. The status file cannot assert what the repository contradicts. |
| **evidence** | A recorded command, artifact or CI run, tied to a commit SHA | The checker verifies the evidence exists and is not stale. It does not re-run the command. |
| **manual** | Requires human architectural or security judgment | A human. The checker reports it and never satisfies it. |

Evidence recorded against a commit that is no longer `HEAD` is reported as
**stale**. A green record cannot outlive the code it described.

---

## 0.1.0a3 — Integration Alpha

**Proves:** the major subsystems coexist coherently. Core runtime, dependency
injection, execution plans, schemas, policies, structured failures, HTTP/ASGI,
OpenAPI, MCP, CLI, introspection, discovery, authorization and redaction,
telemetry, the OpenTelemetry bridges and the Explorer are one system rather
than a collection of parts that happen to share a repository.

**Does not prove:** that anyone outside this repository can use it. That is
`0.1.0a4`.

| Gate | Kind | Mandatory |
| --- | --- | --- |
| Full supported test suite passes | evidence | yes |
| Package build succeeds | evidence | yes |
| Clean-environment installation smoke test succeeds | evidence | yes |
| Python 3.14 baseline verified | automated | yes |
| HTTP integration tests pass | evidence | yes |
| MCP integration and conformance tests pass | evidence | yes |
| CLI smoke tests pass | evidence | yes |
| No known release-blocking regression | evidence | yes |
| Public documentation reflects the implementation | manual | yes |
| Changelog accurately describes changes since `0.1.0a2` | automated | yes |
| Security and release checks required by `QUALITY_GATES.md` | manual | yes |
| Version references are internally consistent | automated | yes |

**Note on the security gate.** `QUALITY_GATES.md` scopes threat model,
dependency audit, secret scanning, static analysis and a private reporting
channel to "before any release beyond experimental alpha". Whether `0.1.0a3`
is still within that exemption is a maintainer decision, not an automated one.
The checker reports the observed state of each item and refuses to decide.

---

## 0.1.0a4 — Application Alpha

**Proves:** Agnara can be consumed as a framework rather than exercised
internally. The emphasis moves from feature creation to dogfooding.

**Does not prove:** that the public API is stable. That is `0.1.0b1`.

| Gate | Kind | Mandatory |
| --- | --- | --- |
| Every `0.1.0a3` gate still satisfied | automated | yes |
| Reference applications exist and install Agnara as an ordinary dependency | evidence | yes |
| No reference application imports Agnara internals | evidence | yes |
| No reference application requires a monkey patch | evidence | yes |
| Public APIs are sufficient to build them | manual | yes |
| Dependency injection works naturally | manual | yes |
| Capabilities can be declared cleanly | manual | yes |
| HTTP exposure works from an application | evidence | yes |
| MCP exposure works from an application, where applicable | evidence | yes |
| Schemas stay coherent across transports | evidence | yes |
| Policies behave consistently across transports | evidence | yes |
| Failures stay structured across transports | evidence | yes |
| CLI and introspection materially help a developer | manual | yes |
| Documentation is sufficient to reproduce the applications | manual | yes |
| Every framework deficiency found by dogfooding is tracked | evidence | yes |

**Workarounds are feedback, not fixes.** If a reference application needs a
workaround because of Agnara, it is recorded as a framework defect with an
Issue. It is never hidden inside the application.

**Current ecosystem note.** The nine numbered repositories in
`agnara-project` remain frozen historical references for `0.1.0a2` and
`0.1.0a3`; they are not silently rewritten to demonstrate a4 compatibility.
The a4 clean-room audit instead built a compact external consumer from the
published documentation and installed candidate artifacts. Its exact-SHA
evidence is recorded in `release-status.json`. Maintainer-only sufficiency and
developer-experience judgments remain manual.

No adapter is a public-index dependency yet. The clean-room consumer proved
normal wheel installation without an editable checkout or workspace
resolution, and ADR 0073 defined the seven-package publication set that the
tag workflow builds, validates and installs. What `0.1.0a4` did not do was
publish it: the tagged run uploaded the core wheel and was rejected on the
first sibling, because the six new PyPI projects had no pending Trusted
Publisher. That is not a gate this section was measuring, which is the point
ADR 0078 and ADR 0079 make; `0.1.0a5` is where publication is proved. The
second blocker — `agnara-http` declaring no public composition surface — was
resolved by ADR 0071. `docs/releases/release-status.json` tracks the
operational state.

**Guardrail (ADR 0068).** `0.1.0a4` is not the FastAPI release, the Django
release, the SQLAlchemy release or the interoperability release. It may run
small experiments where they validate I1; an experiment lives in
`experiments/`, adds no dependency to any distribution, and is named in no
release note as support. The reason is specific: an integration that hides an
insufficient public API behind a framework-specific convenience turns the
"public APIs are sufficient" gate green and deletes the finding it existed to
surface.

---

## 0.1.0a5 — Publication Recovery

**Outcome:** aborted before upload. The immutable tag exercised publication
readiness, which correctly refused to proceed while the publisher record was
`UNVERIFIED`. No `0.1.0a5` artifact was published.

**Does not prove:** anything new about the runtime. `0.1.0a5` carries the
`0.1.0a4` implementation unchanged; no runtime source file differs.

**Why it exists.** `0.1.0a4` passed every gate in this document and published
one of fourteen artifacts. ADR 0078 records the incident and the decision to
close it with a recovery release rather than by moving a tag or inventing a
post-release; ADR 0079 records what changed in the pipeline.

**Owns:** publish readiness as a claim distinct from code readiness, the
publication order, post-publication completeness verification, the single
source of truth for the reviewed set, and the supply-chain pinning of the
publication path.

| Gate | Kind | Mandatory |
| --- | --- | --- |
| Every `0.1.0a4` gate still satisfied | automated | yes |
| The reviewed publication set is publishable, not merely buildable | automated | yes |
| Every PyPI Trusted Publisher is confirmed for this exact target | manual | yes |
| The release pipeline cannot report success on a partial publication | evidence | yes |
| The `0.1.0a4` partial publication is recorded truthfully and not rewritten | evidence | yes |
| Package build succeeds | evidence | yes |
| Clean-environment installation smoke test succeeds | evidence | yes |
| Full supported test suite passes | evidence | yes |
| No known release-blocking regression | evidence | yes |

**On the manual gate.** `pypi-trusted-publishers` is manual because it is the
only kind of gate that can be honest about it. No check running in this
repository can observe PyPI's publisher table. The repository's job is to
refuse to proceed without a recorded human confirmation naming the exact target
version, which is what `docs/releases/publication.json` is.
`scripts/check_publication_readiness.py` fails while any project is
`UNVERIFIED`, and `release.yml` runs it before the first upload.

**Guardrail.** `0.1.0a5` is historical and immutable. It is not resumed,
retagged or published manually. Publication recovery continued in `0.1.0a6`.

---

## 0.1.0a6 — Publication Recovery

**Proves:** that the seven distributions this repository builds can be
published as one complete, verified set, and that the pipeline cannot report
success when they are not.

**Does not prove:** anything new about the runtime. It carries the A5 runtime
unchanged and owns only versioned release metadata and refreshed evidence.

| Gate | Kind | Mandatory |
| --- | --- | --- |
| Every `0.1.0a5` code and release-system gate still satisfied | automated | yes |
| The reviewed publication set is publishable, not merely buildable | automated | yes |
| Every PyPI Trusted Publisher is confirmed for this exact target | manual | yes |
| No `0.1.0a6` file exists before the first upload | automated | yes |
| Package build and clean-environment installation succeed | evidence | yes |
| Full supported test suite and security checks pass | evidence | yes |
| No known release-blocking regression | evidence | yes |

Publication readiness was satisfied by a recorded owner confirmation, but the
first upload proved that the private Pending Trusted Publisher configuration
still did not match `agnara-a2a`. A6 published nothing and remains immutable.

---

## 0.1.0a7 — Publication and Security Recovery

**Outcome:** aborted before upload. The immutable `v0.1.0a7` tag was created
while `docs/releases/publication.json` was still `UNVERIFIED`, and publication
readiness stopped the workflow before its first upload. No `0.1.0a7` artifact
was published. The three release-blocking CodeQL findings it fixed remain
fixed.

**What it proved.** The fourth consecutive attempt confirmed that the gates
were right every time and positioned wrongly every time: a tag pushed by hand
is created before the gates run, so a gate that refuses afterwards cannot
save the version. That is the finding `0.1.0a8` closes.

| Gate | Kind | Mandatory |
| --- | --- | --- |
| Every `0.1.0a6` code and release-system gate still satisfied | automated | yes |
| Every exact PyPI Project name and Trusted Publisher tuple is confirmed | manual | yes |
| No `0.1.0a7` file exists before the first upload | automated | yes |
| The three release-blocking CodeQL findings are closed by fixes | evidence | yes |
| Package build and clean-environment installation succeed | evidence | yes |
| Full supported test suite and security checks pass | evidence | yes |

---

## 0.1.0a8 — Release Pipeline Recovery

**Proves:** that a release can no longer consume a version before every gate
has passed, a human has approved it, and PyPI holds and confirms all seven
distributions. The tag is created by the `workflow_dispatch` run from `main`
after validation, build, clean-room install, index preflight, the `pypi`
environment approval, publication and post-release verification — never by
hand, never first, never without a verified publication (ADR 0082).

**Does not prove:** anything new about framework behavior. It carries the A7
runtime unchanged.

**Owns:** the dispatch-driven release workflow,
`scripts/check_release_preconditions.py`, schema 2 of the publication record
in which registry facts are versioned and the per-release authorization is the
environment approval, and the regression tests that hold the order.

| Gate | Kind | Mandatory |
| --- | --- | --- |
| Every `0.1.0a7` code and release-system gate still satisfied | automated | yes |
| No tag exists until PyPI holds and verifies all seven distributions, and every gate precedes publication | automated | yes |
| Publication requires the `pypi` environment and the approved tag | automated | yes |
| The GitHub Release requires verified publication | automated | yes |
| Every PyPI Trusted Publisher readback is confirmed by a human after the A6 failure | manual | yes |
| The `pypi` environment requires reviewers and restricts deploying branches | manual | yes |
| No `0.1.0a8` tag or file exists before the approved run | automated | yes |
| Package build and clean-environment installation succeed | evidence | yes |
| Full supported test suite and security checks pass | evidence | yes |

**On the two manual gates.** The repository cannot observe PyPI's publisher
table or set GitHub environment protection. It can refuse to proceed without a
dated human readback recorded in `publication.json`, and it can read the
environment's protection rules through the API and refuse while there are
none. Both refusals happen before any tag exists.

---

## 0.1.0a9 — Execution Alpha

**Proves:** execution has the semantics the rest of the architecture waits on.
Streaming exists as one model rather than per adapter; an execution identity
outlives a single invocation; declared idempotency changes runtime behaviour;
and the cost of the framework is measured rather than assumed.

**Does not prove:** that the ecosystem can use Agnara. That is `0.1.0b1`.

**Owns:** I2 streaming model, I3 execution identity and idempotency behaviour,
I14 performance budgets, and the prerequisites already recorded for them.

| Gate | Kind | Mandatory |
| --- | --- | --- |
| Every `0.1.0a8` gate still satisfied | automated | yes |
| The streaming model is decided in an accepted record | evidence | yes |
| A streaming capability behaves identically in direct invocation and in at least one adapter | evidence | yes |
| Cancellation, backpressure and post-partial failure are specified and tested | evidence | yes |
| Execution identity exists and outlives one invocation | evidence | yes |
| Declared idempotency changes runtime behaviour rather than only metadata | evidence | yes |
| A non-idempotent capability is never retried automatically | evidence | yes |
| Performance budgets exist for the compiled paths | evidence | yes |
| A regression against a budget fails CI | automated | yes |
| Benchmarks remain engineering measurements, not rankings | manual | yes |
| No known release-blocking regression | evidence | yes |

**Guardrail (ADR 0068, renumbered through ADR 0081 and ADR 0082).** `0.1.0a9` is not the
ecosystem integration release, the composition beta or a plugin marketplace. It may use an external
integration as an experimental fixture where that genuinely helps validate
streaming, idempotency or performance, and must not publish the fixture as a
contract.

---

## 0.1.0b1 — Interoperability and Composition Beta

**Proves:** two things, and the second is what makes the first credible.

The fundamental public architecture is expected to remain recognizable, and a
developer can build meaningful applications without knowing Agnara's
internals — the original beta thesis.

And the Python ecosystem can use Agnara while Agnara uses the ecosystem:
standalone, as a host of external infrastructure, embedded inside a framework
that already owns the process, and side by side with one in the same
application. `docs/INTEROPERABILITY.md` owns the contract, the integration
matrix and the conformance scenario; I20 owns the work; RFC 0008 holds the
questions that must be answered before any of it is implemented.

**Beta does not mean production-ready.**

**A green I8 is not sufficient.** Composition inside Agnara and composition
with the ecosystem are different claims. This release closes only when the
interoperability gates below carry evidence, not when the initiative that
enables them is marked done.

| Gate | Kind | Mandatory |
| --- | --- | --- |
| Every `0.1.0a9` gate still satisfied | automated | yes |
| The supported public API surface is identified | evidence | yes |
| Public API is distinguished from internals | automated | yes |
| Accidental exports audited | evidence | yes |
| Stability expectations documented | evidence | yes |
| Unnecessary breaking changes minimized | manual | yes |
| One capability exercised through direct Python, HTTP and MCP without duplicating domain logic | evidence | yes |
| Several non-trivial applications cover different framework concerns | evidence | yes |
| A new developer can install, model, build, expose, police, inspect, test and debug from the documentation alone | manual | yes |
| Full CI green | evidence | yes |
| Security gates green | manual | yes |
| Dependency audit acceptable | evidence | yes |
| Static analysis acceptable | evidence | yes |
| Secret scanning acceptable | evidence | yes |
| No unresolved P0/P1 framework defect | evidence | yes |

The cross-transport proof is the first architectural thesis under test:

```text
        one capability
              │
   ┌──────────┼──────────┐
   │          │          │
Direct     HTTP        MCP
Python
```

### Interoperability gates

The second thesis. Every gate below is mandatory, and each is satisfied by a
conformance run against the scenario in `docs/INTEROPERABILITY.md` section 9,
not by a demonstration.

| Group | Gate | Kind | Mandatory |
| --- | --- | --- | --- |
| Web | Starlette hosts and is hosted by Agnara | evidence | yes |
| Web | FastAPI hosts and is hosted by Agnara | evidence | yes |
| Web | Django invokes Agnara capabilities | evidence | yes |
| Web | One further framework, Flask or Litestar | evidence | yes |
| Persistence | SQLite through a dependency-provided repository | evidence | yes |
| Persistence | PostgreSQL with pooling, transaction scope and cleanup | evidence | yes |
| Persistence | SQLAlchemy synchronous | evidence | yes |
| Persistence | SQLAlchemy asynchronous, where the driver applies | evidence | yes |
| Schema | Standard-library adapter remains a first-class path | evidence | yes |
| Schema | Pydantic adapter | evidence | yes |
| Schema | A second non-stdlib adapter, ideally msgspec, if ready | evidence | yes |
| Presentation | Jinja2 or an equivalent HTML rendering path | evidence | yes |
| Background | At least one real task runtime, preferably Celery | evidence | yes |
| Observability | OpenTelemetry validated end to end across HTTP, workers and errors | evidence | yes |
| Protocol composition | HTTP and MCP over one shared capability, no duplicated logic | evidence | yes |
| Embedding | FastAPI hosts Agnara | evidence | yes |
| Embedding | Django hosts Agnara | evidence | yes |
| Side-by-side | One ASGI application serving native routes and Agnara exposures | evidence | yes |
| Progressive adoption | An existing application adopts Agnara without a full rewrite | evidence | yes |
| Kernel | `agnara` still imports only the standard library | automated | yes |
| Kernel | Every shipped integration passes the anti-coupling test | manual | yes |

**Changing one of these is an ADR or RFC**, carrying the evidence that it was
wrong. A gate is never quietly dropped, relaxed or made non-mandatory during
release preparation, which is when the pressure to do so peaks.

**Deliberately not blocking.** GraphQL, gRPC, Sanic, Quart, Falcon, aiohttp,
Robyn, Prefect, Kafka, NATS, and Temporal if I6 is not mature enough, stay in
research. Each is either an unanswered semantic mapping, a duplicate of
evidence another gate already produces, or dependent on an initiative that is
not finished. `docs/INTEROPERABILITY.md` section 6 records which reason
applies to which.

---

## 0.1.0rc1 — Release Candidate

**Proves:** stability. Not features.

| Gate | Kind | Mandatory |
| --- | --- | --- |
| Every `0.1.0b1` gate still satisfied | automated | yes |
| Beta received meaningful real-world dogfooding | evidence | yes |
| No known critical architectural defect | manual | yes |
| No unresolved release-blocking security issue | manual | yes |
| Public API changes have slowed substantially | evidence | yes |
| Reference applications continue working | evidence | yes |
| Backward compatibility explicitly evaluated | manual | yes |
| Documentation complete for the intended `0.1.0` surface | manual | yes |
| Migration guidance exists where necessary | evidence | yes |
| Packaging and publishing workflows reproducible | evidence | yes |
| Clean-environment installation succeeds | evidence | yes |
| Supported transports behave consistently | evidence | yes |
| Observability sufficient to diagnose framework behavior | manual | yes |
| No known catastrophic performance regression | evidence | yes |
| All quality gates pass | evidence | yes |

**From this point, major architecture is introduced only to remove a blocker.**

---

## 0.1.0 — First Stable Release

**Proves:** enough architectural coherence, documentation, testing, security
and external usability to establish a first stable public contract.

**Does not mean feature-complete.**

| Gate | Kind | Mandatory |
| --- | --- | --- |
| RC validation completed successfully | evidence | yes |
| No known P0/P1 defect | evidence | yes |
| No known critical security vulnerability | manual | yes |
| Public API explicitly identified | evidence | yes |
| Compatibility expectations documented | evidence | yes |
| Documentation reviewed from a new-user perspective | manual | yes |
| Multiple external or reference applications validated | evidence | yes |
| Direct execution and supported transports validated | evidence | yes |
| Packaging, install and release pipeline fully verified | evidence | yes |
| PyPI metadata correct | evidence | yes |
| README correct | manual | yes |
| Changelog complete | automated | yes |
| Quality gates complete | evidence | yes |
| Security gates complete | manual | yes |
| License and project metadata correct | automated | yes |
| Repository is clean | automated | yes |
| Release commit unambiguously identified | automated | yes |

---

## Operating rules

**Feature freeze.** When only release validation remains for the current
target, `docs/releases/release-status.json` records
`FEATURE FREEZE RECOMMENDED`. During that stage the priorities are regressions, documentation, tests, compatibility, security,
packaging, release notes, cleanup and dogfooding.

**Transition.** When a target becomes `RELEASE_READY`, the current target does
**not** advance automatically. The owner is told, given the evidence for every
mandatory gate, the remaining non-blocking issues, proposed release notes, the
release-closing checklist and a recommendation. `current_target` changes only
after the owner confirms the release was published.

**Nothing is published without explicit authorization.** No tag, no GitHub
Release, no `develop` → `main` merge, no PyPI upload. `release.yml` is
dispatched by the owner from `main` and publishes through Trusted Publishing
only after a reviewer approves the run in the `pypi` environment; the tag is
created by that approved run and by nothing else (ADR 0082). This plan never
creates one.

**Do not inflate.** A release does not advance because many features landed.
Implementing a feature to raise a percentage defeats the purpose of measuring.

## Running the check

```bash
uv run python scripts/check_release_readiness.py
```

Add `--json` for the machine-readable result, `--verbose` for per-gate
evidence. The command re-derives every automated gate from the repository, so
it disagrees with `release-status.json` when the file is wrong — which is the
point.
=======
`docs/releases/release-status.json` records current gate state.
`QUALITY_GATES.md` and `docs/MAINTAINERS_RELEASE.md` own the operational
procedure; this plan owns only the product bar.
>>>>>>> 15cdde3ccb0211665dc88e153872be1acdeee5aa
