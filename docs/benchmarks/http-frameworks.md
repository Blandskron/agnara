# HTTP Framework Benchmark

## Purpose

This benchmark measures a narrow warm in-process ASGI boundary for E6.10. It
compares one `GET /benchmark` exchange returning `{"value":42}` through:

1. a direct ASGI reference with manual route matching and JSON serialization;
2. Starlette 1.6.0 routing and `JSONResponse`;
3. a typed FastAPI 0.141.1 route and JSON response;
4. a typed Litestar 2.24.0 route and JSON response;
5. Agnara's compiled route, protocol-neutral capability invocation and JSON
   response.

The applications and Agnara execution plan are built before timing. Each
measured operation creates the same ASGI scope, request event and response
collector. Correctness is checked after every warmup and after the timer stops
for every timed batch. The garbage collector is disabled only around timed
samples and restored afterward.

This is not a production throughput benchmark. It excludes the ASGI server,
socket, HTTP parser, network, application construction, startup, concurrency
and deployment configuration. Starlette performs no typed input validation in
this empty-input scenario. FastAPI and Litestar retain their typed route
machinery; Agnara also crosses its capability runtime boundary. The result is
useful only with those semantic differences visible.

## Reproducibility

The competitor versions are exact development pins and do not enter any
distributable Agnara package. From the repository root:

```bash
uv sync
uv run python benchmarks/http_frameworks.py
uv run python benchmarks/http_frameworks.py \
  --iterations 5000 --samples 11 --warmups 3 --json
```

The JSON contract records raw elapsed samples, nanoseconds per request,
minimum, median, mean, maximum and sample standard deviation. It also records
the deterministic rotating order, framework versions, sampling controls,
measurement boundary, Git state, Python/GIL/platform/processor/clock metadata
and median ratios to the direct ASGI reference. The order rotates on every
sample so no framework permanently owns the first or last position.

## Recorded baseline

Two consecutive runs were retained instead of selecting the more favorable
one:

```text
recorded at: 2026-09-04T02:33:46.970015+00:00 and 2026-09-04T02:34:08.019941+00:00
source base commit: 4eb6090d162831becf194cbae619f76f2b070703
dirty: true (Issue #159 benchmark implementation under measurement)
command: .venv\Scripts\python.exe benchmarks\http_frameworks.py --iterations 5000 --samples 11 --warmups 3 --json
platform: Windows 11 10.0.26200 (AMD64)
processor: Intel64 Family 6 Model 140 Stepping 1, GenuineIntel
logical CPU count: 8
Python: CPython 3.14.4 (tags/v3.14.4:23116f9, Apr 7 2026 14:10:54)
GIL enabled: true
timer: QueryPerformanceCounter(), 100 ns reported resolution
server / workers / network / concurrency: excluded
```

| Scenario | First median ns/request | Second median ns/request | Observed median range | Ratio range to direct ASGI |
| --- | ---: | ---: | ---: | ---: |
| Direct ASGI | 5,604.52 | 4,801.90 | 4,801.90–5,604.52 | 1.00x |
| Starlette | 16,229.64 | 13,586.20 | 13,586.20–16,229.64 | 2.83–2.90x |
| FastAPI | 55,759.04 | 49,373.96 | 49,373.96–55,759.04 | 9.95–10.28x |
| Litestar | 38,434.10 | 35,783.36 | 35,783.36–38,434.10 | 6.86–7.45x |
| Agnara HTTP | 47,626.10 | 41,633.54 | 41,633.54–47,626.10 | 8.50–8.67x |

The direct reference itself moved by about 17% between medians, and individual
sample dispersion was material. Ratios therefore amplify baseline movement
and must not be read as precise portable constants. On this machine and this
single scenario, Agnara's absolute median was about 41.6–47.6 microseconds per
in-process request: below FastAPI, above Litestar and materially above minimal
Starlette. This does not establish production throughput, framework
superiority, performance on another system or a stable regression budget.

## Architectural interpretation

E6.9 asked whether Agnara should replace its direct ASGI adapter with a
Starlette dependency. The measurement confirms that minimal Starlette is a
useful lower-semantic-layer reference, not that adopting it would remove
Agnara's required capability invocation, binding, policy, result and problem
semantics. Adding Starlette would preserve most of those costs while coupling
the adapter to another framework. The direct ASGI decision in ADR 0006
therefore stands. Revisit only if a concrete missing feature or separately
profiled bottleneck changes that tradeoff.

## Sources

- https://pypi.org/project/fastapi/0.141.1/
- https://pypi.org/project/starlette/1.6.0/
- https://pypi.org/project/litestar/2.24.0/
- https://asgi.readthedocs.io/en/latest/
