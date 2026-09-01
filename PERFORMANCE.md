# Performance Strategy

## Principle

Agnara must be fast by architecture, not by unsupported claims.

## Optimization order

1. eliminate unnecessary work;
2. move reflection to startup;
3. freeze immutable structures;
4. avoid allocations on hot paths;
5. cache compiled binders/serializers safely;
6. benchmark;
7. optimize Python;
8. consider native acceleration only with evidence.

## Benchmark competitors

At minimum:

- FastAPI;
- Starlette;
- Litestar;
- Agnara direct invocation;
- Agnara HTTP;
- FastMCP for comparable MCP scenarios.

Servers should be separated from frameworks in reporting.

Candidate servers:

- Uvicorn;
- Granian.

## Benchmark scenarios

### Startup

- 1 capability;
- 100;
- 1,000;
- 10,000.

Measure:

- wall time;
- peak memory;
- compiled plan count.

### HTTP

- plain text;
- small JSON;
- nested validation;
- query/path binding;
- one dependency;
- ten dependencies;
- error path;
- streaming.

### Core

- direct invocation;
- dependency lookup;
- policy evaluation;
- schema validation;
- execution dispatch.

### Concurrency

Test conventional CPython and free-threaded CPython separately.

Do not assume free-threading improves async HTTP workloads automatically.

## Performance budget

Every abstraction added to core should have measurable overhead.

Maintain a regression dashboard once benchmark noise is understood.

## Rust policy

Rust is allowed only after an ADR that includes:

- measured bottleneck;
- expected gain;
- FFI cost;
- wheel strategy;
- Python 3.14t implications;
- fallback behavior;
- maintenance cost.
