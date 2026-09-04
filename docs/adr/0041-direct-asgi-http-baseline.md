# ADR 0041 — Retain the Direct ASGI HTTP Baseline

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #159

## Context

ADR 0006 selected a dependency-free ASGI boundary but left a minimal Starlette
dependency open to later evidence. E6.9 and E6.10 require that comparison to
be explicit and prevent architecture from being chosen by reputation or an
unqualified benchmark chart.

A framework comparison is easy to misstate. An in-process callable excludes
the server and network, while a minimal toolkit route does less semantic work
than Agnara's capability dispatch. Conversely, a production server benchmark
can mostly measure the chosen server. The evidence must name its boundary and
retain the different work performed by each scenario.

## Decision

Agnara retains its direct ASGI boundary. It does not add Starlette, FastAPI or
Litestar to `agnara-http`.

The E6.10 harness measures one complete warm in-process ASGI request and
response with prebuilt applications. A direct reference, Starlette, FastAPI,
Litestar and Agnara return the same JSON value. Samples use deterministic
rotating order, validate correctness outside each timed batch and record raw
measurements, dispersion, environment, versions and Git state. Servers,
sockets, protocol parsing, startup and network are explicitly excluded.

The initial Windows/CPython 3.14.4 measurements place Agnara HTTP at roughly
41.6–47.6 microseconds median for this scenario. Minimal Starlette is faster,
but it does not perform Agnara's capability invocation, binding, policy,
result and problem semantics. Adding it underneath Agnara would not replace
that work and would introduce framework coupling without a demonstrated
functional or performance benefit.

These figures are evidence about one machine and one scenario, not a portable
ranking or CI budget. `docs/benchmarks/http-frameworks.md` owns the exact
measurements and limitations.

## Consequences

- E6.9 is resolved without adding a runtime dependency.
- FastAPI, Starlette and Litestar remain exact development-only benchmark
  fixtures.
- The benchmark gives later optimizations a reproducible HTTP reference, but
  CI asserts its contract and correctness rather than timing thresholds.
- Server selection and network throughput remain separate measurements.
- Future adoption of an ASGI toolkit requires new functional evidence or a
  profile showing that it removes a real bottleneck while preserving Agnara's
  semantics.

## Guardrails

- Competitor packages may not enter any distributable Agnara dependency list.
- Reports must state framework versions and the included/excluded boundary.
- Never compare development-mode servers with optimized competitors.
- Never generalize one workstation's ratios to production, concurrency,
  free-threading or other Python/platform builds.
- Preserve correctness checks and deterministic interleaving when extending
  the harness.
- Do not optimize or introduce native code from this result alone.

## Evidence

- `benchmarks/http_frameworks.py`
- `tests/benchmarks/test_http_framework_benchmark.py`
- `docs/benchmarks/http-frameworks.md`
- https://pypi.org/project/fastapi/0.141.1/
- https://pypi.org/project/starlette/1.6.0/
- https://pypi.org/project/litestar/2.24.0/
