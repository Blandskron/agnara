# Agnara Release Plan

This document defines the progressive path from the published `0.1.0a2` to the
first stable `0.1.0`. It is a **measurement mechanism, not a feature backlog**.
`BACKLOG.md` decides what gets built; this decides when what has been built is
mature enough to close a release.

## Path

```text
0.1.0a2  (published 2026-09-04)
   ↓
0.1.0a3     subsystem integration
   ↓
0.1.0a4     external application validation
   ↓
0.1.0b1     usable public framework contract
   ↓
0.1.0rc1    stability candidate
   ↓
0.1.0       first stable contract
```

**No release carries a calendar date.** A release closes when its exit gates
are satisfied by evidence, never when a date arrives and never because a
readiness percentage looks high. The difference between these releases is
evidence and maturity, not feature count.

## How this relates to existing rules

This plan **supplements** the repository's existing requirements and never
relaxes them. Where it appears looser than an existing rule, the existing rule
wins:

| Authority | Owns |
| --- | --- |
| `QUALITY_GATES.md` | Definition of done, required checks, security gates, changelog and release consistency gate, merge governance, attribution |
| `SECURITY.md` | Security boundaries, reporting channel, claims discipline |
| `docs/MAINTAINERS_RELEASE.md` | The operational release procedure, Trusted Publishing, tagging |
| `docs/adr/0021-*.md` | Synchronized pre-one versions and changelog structure |
| This plan | *When* the current state is mature enough to enter that procedure |

Two file conventions coexist deliberately:

- `docs/releases/v<version>.md` — the **user-facing release note**, the
  existing convention, written for whoever installs the package.
- `docs/releases/history/<version>.md` — the **maturity snapshot**, written for
  whoever asks later what a release actually proved and on what evidence.

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

**Current ecosystem note.** As of this plan's creation no repository under the
owner's account consumes Agnara; the other projects are unrelated Django
applications. `0.1.0a4` therefore requires reference applications to be
created or identified before its gates can produce any evidence at all.

---

## 0.1.0b1 — First Beta

**Proves:** the fundamental public architecture is expected to remain
recognizable, and a developer can build meaningful applications without
knowing Agnara's internals.

**Beta does not mean production-ready.**

| Gate | Kind | Mandatory |
| --- | --- | --- |
| Every `0.1.0a4` gate still satisfied | automated | yes |
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

The cross-transport proof is the architectural thesis under test:

```text
        one capability
              │
   ┌──────────┼──────────┐
   │          │          │
Direct     HTTP        MCP
Python
```

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
target, `STATUS.md` records `FEATURE FREEZE RECOMMENDED`. During that stage the
priorities are regressions, documentation, tests, compatibility, security,
packaging, release notes, cleanup and dogfooding.

**Transition.** When a target becomes `RELEASE_READY`, the current target does
**not** advance automatically. The owner is told, given the evidence for every
mandatory gate, the remaining non-blocking issues, proposed release notes, the
release-closing checklist and a recommendation. `current_target` changes only
after the owner confirms the release was published.

**Nothing is published without explicit authorization.** No tag, no GitHub
Release, no `develop` → `main` merge, no PyPI upload. `release.yml` publishes
on a pushed `v*.*.*` tag through Trusted Publishing; this plan never creates
one.

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
