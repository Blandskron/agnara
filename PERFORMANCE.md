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

The E6.10 in-process HTTP comparison is implemented by
`benchmarks/http_frameworks.py` and recorded in
`docs/benchmarks/http-frameworks.md`. It separates framework cost from server
and network cost, rotates scenario order and retains raw samples. ADR 0041
keeps the direct ASGI boundary; the result is not a portable ranking or CI
latency threshold.

The E9.6 telemetry cost measurement is implemented by
`benchmarks/telemetry_overhead.py` and recorded in
`docs/benchmarks/telemetry-overhead.md`. It separates the port's fixed cost
from the cost of having any observer and from each OpenTelemetry adapter, with
in-memory exporters so no network or serialization cost is included. It is what
justified guarding lifecycle event construction behind hook presence (ADR
0058); the same caveats apply, and the hooked scenarios are explicitly not a
claim in either direction on the machine used.

The E7.9 in-process MCP comparison is implemented by
`benchmarks/mcp_tool_invocation.py` and recorded in
`docs/benchmarks/mcp-tool-invocation.md`. FastMCP is `MCPServer` in the pinned
`mcp==2.1.1`. It measures the handler boundary and the official client
boundary separately, and reports synchronous and asynchronous tools
separately because the SDK runs a synchronous tool in a worker thread. The
same caveats apply: no portable ranking, no throughput claim, no threshold.

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
