# Python 3.15 Readiness

**Horizon:** future Agnara 1.x research

**Status:** `PLANNED`

**Planning issue:** [#466](https://github.com/Blandskron/agnara/issues/466)

This is the canonical program specification: activation, work-package scope,
acceptance evidence and runtime comparisons. [BACKLOG](../../BACKLOG.md) owns
task state; [INITIATIVES](../INITIATIVES.md) indexes the program;
[MATURITY](../MATURITY.md) owns claims about what exists today. Planning an
experiment is not a decision to adopt its subject.

## Research boundary and activation

Agnara currently requires **Python >=3.14**. Python 3.15 support is not claimed
by the current package metadata or CI. This document is a research plan, not
an implementation authorization or a release gate.

Activation requires a separately reviewed issue and maintainer decision that
sets scope, owners and validation resources. At that point, create executable
issues from P315-01 through P315-12 as needed, preserving their dependencies
and acceptance criteria. Until activation, no 3.15 runtime, dependency,
packaging, API or workflow changes are part of this program.

The intended Agnara 1.x position, **only after the support gate passes**, is a Python >=3.14 baseline
with conventional CPython 3.14 and 3.15 validated; 3.15 free-threading has its
own evidence and maturity decision. Raising the minimum requires a later ADR
and supporting evidence. Initial compatibility with 3.14 is mandatory.

## Work packages and dependency order

Priorities express research order, not GitHub label requirements.
Every package depends on activation. P315-11 can collect dependency evidence
alongside P0 work; its closure is required for ecosystem conclusions, not for
starting isolated core validation. Conventional support does not wait for
optional JIT, lazy-import, frozendict or sentinel adoption.

| ID | Priority | Work | Additional prerequisites for closure |
| --- | --- | --- | --- |
| P315-01 | P0 | Conventional compatibility | P315-11 conventional dependency evidence |
| P315-02 | P0 | Independent 3.15t validation: core, then ecosystem | P315-03; P315-11 for ecosystem |
| P315-03 | P0 | Free-threading concurrency audit | Audited ownership and reproducible race evidence |
| P315-04 | P1 | Conventional 3.14 vs 3.15 baseline | P315-01 correctness for measured paths |
| P315-05 | P1 | Conventional 3.15 vs 3.15t measurements | P315-02 and P315-03 for measured scope |
| P315-06 | P2 | JIT experiment | P315-04; P315-05 if a combined build is eligible |
| P315-07 | P1 | Profiling / Tachyon | P315-01 correctness for profiled paths |
| P315-08 | P2 | Lazy imports research | P315-01 and P315-07 |
| P315-09 | P2 | frozendict research | P315-03 and P315-07 |
| P315-10 | P2 | Sentinel research | P315-01; 3.14 compatibility review |
| P315-11 | P1 | Dependency compatibility matrix | Exact resolved/build evidence per cell |
| P315-12 | P3 | Official support declaration | P315-01, P315-04, P315-11 and final support gate |

### P315-01 — CPython 3.15 compatibility

Run the complete suite and architecture gates on conventional CPython 3.15
while retaining the 3.14 reference lane. Cover kernel, HTTP, MCP, CLI,
telemetry, public API, dependency resolution, packaging and clean-room wheel
installation/import of the complete distribution set. Include browser and
integration lanes required by [QUALITY_GATES](../../QUALITY_GATES.md).

Deliver a commit-linked report with exact interpreter/dependency versions,
commands, OS, pass/fail/skip results and classified failures. Revalidate on a
final CPython 3.15 build before declaring support; prerelease success alone
does not close P315-12. No minimum-version increase follows from passing.

### P315-02 — CPython 3.15 free-threaded

Design an independent future CPython 3.15t lane, separating:

- **Core:** stdlib-only kernel installation/import and focused kernel,
  architecture and concurrency evidence, with test tooling accounted for.
- **Ecosystem/adapters:** HTTP, MCP, CLI, telemetry and optional host/schema
  fixtures, each with its own dependency and platform results.

Record build identity, free-threading configuration and actual GIL state
before and after dependency imports and during the workload. An extension
that re-enables the GIL invalidates that cell as free-threaded evidence; record
it as blocked with the dependency identified. Never silently force the GIL on
to turn a failure green. Installation alone is not concurrency validation.

Acceptance requires P315-03 evidence, failure attribution and repeatable
correctness/cancellation/cleanup runs on each claimed platform. A passing
isolated core cell cannot promote the whole ecosystem. No free-threaded
compatibility claim precedes the audit.

### P315-03 — Free-threading concurrency audit

Inventory every stateful object with owner, lifetime, mutation sites,
publication/freeze point, thread/event-loop access contract, synchronization
and a reproducer or justified confinement rule. Start from these existing
boundaries (paths are inspection entry points, not a safety verdict):

| Surface | Entry point / audit focus |
| --- | --- |
| CapabilityRegistry and exposure registries | `packages/agnara/src/agnara/capability/registry.py`, `packages/agnara/src/agnara/exposure/registry.py`: freeze, publication and concurrent iteration |
| DI registry, singleton creation and caches | `packages/agnara/src/agnara/core/di/`: check-then-act, provider failure/cancellation, initialization and teardown ownership |
| Idempotency store | `packages/agnara/src/agnara/execution/idempotency.py`: atomic claims/completion, expiry, eviction and stale handles |
| Compiled plans and nested invocation | `packages/agnara/src/agnara/execution/`: shared plan references, child isolation, cancellation, deadlines and recursion |
| Policy evaluation and execution context | `packages/agnara/src/agnara/policy/`, `packages/agnara/src/agnara/execution/`: authority isolation, mutable values and context propagation |
| Telemetry hooks | `packages/agnara/src/agnara/execution/telemetry.py`, `packages/agnara-telemetry/src/agnara_telemetry/`: hook/exporter ownership and concurrent span state |
| HTTP registries and caches | `packages/agnara-http/src/agnara_http/`: routing snapshots, schema/UI caches and request isolation |
| MCP registries and caches | `packages/agnara-mcp/src/agnara_mcp/`: tool snapshots, authorization maps and per-call state |

Extend the inventory to any other state shared between threads. Search for
data races, check-then-act races, mutation after freeze (including mutable
values behind read-only mappings), accidental GIL-dependent caches, concurrent
iteration, missing locks and unnecessary locks. An asyncio lock does not by
itself establish a cross-thread contract. Respect existing event-loop/lifecycle
ownership; this program does not silently promise cross-loop runtime reuse.

Acceptance: reviewed inventory plus deterministic barrier-controlled race
tests and bounded stress evidence under an actually disabled GIL. Include
failure, cancellation and cleanup; assign every finding a disposition and
regression test before claiming the affected boundary is compatible. Any
policy-order or lifecycle change requires the existing ADR/review discipline.

### P315-04 — Conventional benchmark baseline

Compare conventional CPython 3.14 and 3.15 using the runtime matrix and existing
methodology below. Cover startup, compilation, invocation, dependency
resolution, policies, schema validation, HTTP, MCP, telemetry, idempotency,
nested composition, streaming and memory. Record missing workload coverage as
a future task; never silently substitute a different workload for one runtime.
Acceptance is a reproducible report with raw evidence and benchmark sanity,
not a required speedup. Preserve all current performance budgets.

### P315-05 — Free-threaded benchmark

Compare conventional 3.15 with 3.15t separately from the version comparison.
Measure CPU-bound concurrency, concurrent capabilities, shared registries,
DI, async plus threads, HTTP and MCP, including synchronization and memory
costs. Keep thread counts, event-loop ownership, workload and external services
equivalent. **Free-threaded Python is not assumed faster than conventional
CPython; it will be measured.** Acceptance requires validated correctness for
the measured scope, disabled-GIL evidence and retained raw samples.

### P315-06 — JIT experiment

Classification: **EXPERIMENT**; never an Agnara requirement. Compare conventional
3.15 with 3.15 + JIT through the existing benchmark workloads. Check upstream
build/platform eligibility before adding any combination. Compare 3.15t with
3.15t + JIT only if CPython actually supports that combination at execution
time; otherwise record it as ineligible, not as a missing Agnara feature.

Separate cold start from warmed steady state and record JIT availability and
enabled state outside timed samples. Deliver reproducible observations and a
retain/reject recommendation; an optimization requires evidence and a separate
reviewed change. JIT findings cannot gate ordinary 3.15 compatibility.

### P315-07 — Profiling / Tachyon

Plan a profiling pass using the applicable 3.15 profiling facilities,
including Tachyon where supported. Inspect CapabilityRuntime, direct invocation,
DI, policy evaluation, schema validation, request binding, serialization, HTTP
and MCP projection, telemetry, idempotency and nested composition.

Retain profiler/build versions, platform/permissions, commands, sampling
configuration, raw profiles and workload identities. Measure profiling
overhead separately; do not use instrumented samples as unprofiled benchmark
results. Acceptance is reproducible hotspot evidence linked to optimization
hypotheses, before any optimization is selected.

### P315-08 — Lazy imports research

Study PEP 810 first in agnara-cli, agnara-http, agnara-mcp and
agnara-telemetry; no automatic kernel adoption. Compare 3.15 eager and lazy
imports for CLI cold start, import time, application/container startup, memory
and dependency loading. Include deferred errors, import side effects, cycles,
concurrent first use and deterministic registration/compilation behavior.

Acceptance is measured benefit/cost plus a semantics and 3.14 compatibility
decision. A future experiment must not introduce 3.15-only syntax into shipped
3.14-compatible modules. Adoption needs its own reviewed decision and tests.

### P315-09 — frozendict research

Compare MappingProxyType with 3.15 frozendict for construction, lookup, memory,
equality, hashing where applicable, serialization, copying, free-threading,
ergonomics and compatibility. Registry, plan, policy and adapter mappings are
candidate inspection sites, not approved migrations. Examine live-view versus
snapshot semantics, nested mutable values and unhashable contents explicitly.

Acceptance is an isolated experiment report and a semantics/compatibility
recommendation. **No frozendict migration while Python 3.14 remains the
baseline.** Any later migration requires a separate architecture decision.

### P315-10 — Sentinel research

Inspect the existing object sentinel in
`packages/agnara/src/agnara/core/di/resolver.py` and `_MISSING = object()` in
`packages/agnara-cli/src/agnara_cli/_target.py`. Compare the standard 3.15
sentinel's identity semantics, typing, serialization, representation, debugging,
internal API impact and Python 3.14 compatibility.

Acceptance is a behavior/compatibility report and a retain/reject/defer
recommendation. Do not migrate current sentinels in this planning change;
future adoption is not preapproved and must preserve the baseline.

### P315-11 — Dependency compatibility matrix

Use current manifests and `uv.lock` as the initial inventory, then record the
exact versions actually resolved. Do not equate an upstream classifier or an
available wheel with passing Agnara integration tests.

| Layer | Required inventory |
| --- | --- |
| Core | `agnara` stdlib-only runtime; keep third-party test tooling separate |
| MCP | Pinned MCP SDK and its transitive dependencies |
| Telemetry | OpenTelemetry API; SDK/exporters as application-owned fixtures |
| Schema fixtures | Pydantic and its native dependencies; msgspec |
| ASGI / hosts | Starlette, FastAPI, Litestar, Django; Uvicorn/Granian only where actually selected for a workload |
| Persistence fixture | SQLAlchemy and the selected driver/backend |
| Testing | pytest, Hypothesis, Playwright and transitive tooling |
| Packaging / tooling | uv, pip, hatchling, wheel/build tooling, Ruff and ty as applicable |

For **each dependency and OS**, record separate conventional 3.15 and 3.15t
cells: exact version, interpreter/ABI, wheel versus source build, resolution,
install/import, integration result, GIL behavior, upstream issue, owner and
evidence link. Start every cell as **NOT RUN**. Distinguish Agnara failures,
dependency failures, unsupported builds and tooling blockers. A third-party
failure is not automatically a core defect. Acceptance requires all claimed
ecosystem cells to pass or explicit exclusions that narrow the claim.

### P315-12 — Support declaration

Conventional support requires commit-linked evidence on **Linux, Windows and
macOS** for the full suite, architecture gates, packaging, wheel installs,
clean-room imports, public API, dependency compatibility, benchmark sanity and
updated documentation. Preserve conventional 3.14 validation on that same
candidate. Review skips/failures explicitly; no required missing evidence may
be converted into support by changing prose. Require final 3.15 build evidence
and maintainer review of the declaration.

Only then may the project say “Requires Python >=3.14; tested on CPython 3.14
and CPython 3.15,” with the precise matrix and limitations linked.

Free-threaded maturity is decided separately, per core/ecosystem and platform:

- **RESEARCH:** current state; design intent without completed validation.
- **EXPERIMENTAL:** audited scope with repeatable disabled-GIL evidence and
  explicit limitations; no broad compatibility commitment.
- **SUPPORTED:** maintained lanes, closed audit findings, dependency and
  platform evidence, regression coverage and an explicit maintainer-approved
  support policy for the claimed scope.

These are future declaration criteria, not a change to MATURITY's present
vocabulary or status. Conventional success cannot promote free-threading.
Optional research rejection does not prevent conventional support.

## Runtime benchmark matrix

This is a future measurement plan, not an enabled lane or result. Execute
nothing before activation. Recheck upstream eligibility for the exact build,
OS and architecture before materializing any lane.

| Candidate runtime | Comparison purpose | Eligibility |
| --- | --- | --- |
| CPython 3.14 conventional | Reference baseline | Existing baseline |
| CPython 3.15 conventional | Version comparison against 3.14 | Correctness validated first |
| CPython 3.15 + JIT | JIT on/off comparison | Only supported upstream builds/platforms |
| CPython 3.15 free-threaded | GIL/concurrency comparison against conventional 3.15 | Verified disabled GIL; separate core/ecosystem scope |

**Conditional extension, not an admitted matrix row:** CPython 3.15
free-threaded + JIT. Add it only after upstream support for both together is
verified and recorded; otherwise explicitly omit the combination. Listing
two independent CPython options is not proof that they compose.

Reuse [PERFORMANCE](../../PERFORMANCE.md), the existing
[runtime-path methodology](../benchmarks/runtime-paths.md),
[HTTP comparison](../benchmarks/http-frameworks.md),
[MCP comparison](../benchmarks/mcp-tool-invocation.md) and
[telemetry measurement](../benchmarks/telemetry-overhead.md).
Inspect existing `benchmarks/runtime_invocation.py` and
`benchmarks/frozen_value_type_memory.py` when planning additional coverage.

Each paired measurement uses the **same commit, hardware, OS, workload,
iterations, warmups and external configuration**. Hold payloads, dependency
versions, server/workers, concurrency and measurement boundaries constant;
if a dependency must differ, label the result as a confounded comparison.
Record interpreter patch/build/compiler options, GIL/JIT state, commands,
environment, raw samples, correctness checks and memory measurement method.
Keep startup distinct from warmed execution and profiler runs distinct from
timing runs. Use the existing ordering/repetition methodology unchanged.

Never present different-machine results as runtime speedups, local findings
as portable claims, or a set of workloads as a universal ranking. No numbers,
results or new performance budgets are supplied by this plan. Existing
[budget definitions](../performance/README.md) remain unchanged.

## Upstream reference checkpoint

Reviewed on 2026-09-21 against Python's 3.15 prerelease documentation. Recheck
these sources after activation; upstream capability is not Agnara support.

- [PEP 790 release schedule](https://peps.python.org/pep-0790/) schedules the
  final release for October 2026; it does not unlock this program.
- [Python 3.15 changes](https://docs.python.org/3.15/whatsnew/3.15.html)
  describe lazy imports (PEP 810), frozendict (PEP 814), sentinel (PEP 661)
  and profiling/Tachyon (PEP 799). They are research inputs here.
- [Free-threading guide](https://docs.python.org/3.15/howto/free-threading-python.html)
  explains build detection, actual GIL state and extension compatibility.
- [CPython build options](https://docs.python.org/3.15/using/configure.html)
  describe free-threading and experimental JIT configuration; verify the
  selected platform and combination before an experiment.

## Planning-change validation boundary

Review the complete diff and local Markdown targets/anchors, compare roadmap,
backlog, initiatives, maturity, performance and quality-gate statements, and
run existing read-only documentation consistency/encoding checks. Do not run
benchmarks, install runtimes, regenerate artifacts, change tests or execute
implementation validations as part of this documentation-only change.
If a check needs implementation or environment changes, report that limitation
and defer it rather than expanding this PR.
