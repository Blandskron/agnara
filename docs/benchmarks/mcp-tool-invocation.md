# MCP Tool Invocation Benchmark

## Purpose

This benchmark measures a narrow warm in-process MCP `tools/call` boundary for
E7.9. It exists because a discovery-only timing is not invocation evidence, and
because `PERFORMANCE.md` names FastMCP as the comparison for MCP scenarios.
FastMCP is `MCPServer` in the pinned `mcp==2.1.1`; the v1 module now raises on
import.

It is not a production throughput benchmark and not a ranking. It excludes the
network, sockets, JSON-RPC framing, connection establishment, concurrency and
deployment configuration.

## Compared paths

Every scenario exposes the same tool: `echo(value: int) -> int`, called with
`{"value": 41}`, returning `structuredContent {"result": 41}`.

1. `direct_sdk` — a lowlevel official `Server` whose handler does the name
   check, the type check and the result construction by hand. It is the
   reference, not a usable framework.
2. `mcpserver_sync` — an official `MCPServer` tool declared with `def`.
3. `mcpserver_async` — the same tool declared with `async def`.
4. `agnara_mcp_sync` — `build_mcp_server` over a compiled capability declared
   with `def`.
5. `agnara_mcp_async` — the same capability declared with `async def`.

The sync/async split is the point of the design. `MCPServer` runs a
synchronous tool in an anyio worker thread, while Agnara runs a synchronous
handler inline and awaits an asynchronous one. Comparing only synchronous
tools would report that execution policy as dispatch cost.

Two semantic differences remain and are not normalized away:

- `MCPServer` derives and publishes an `outputSchema`, so at the client
  boundary its results are revalidated against jsonschema on every call.
  Agnara publishes none yet, by decision, so it pays nothing there and also
  offers the client nothing to validate.
- Agnara's text block carries the `{"result":41}` envelope ADR 0043 defines;
  the other two carry `41`. The pinned revision leaves that shape to the
  server.

Agnara's measured path additionally includes the declared-scope policy
evaluation ADR 0044 requires, compiled input validation, the empty DI
resolution scope, telemetry event construction and canonical result
projection.

## Measured boundaries

`handler`
: the registered `tools/call` handler alone, driven with a prebuilt request
  context. This is each framework's own dispatch cost. Server middleware,
  params validation and result validation are excluded for every scenario —
  including the `RequestStateBoundary` and OpenTelemetry middleware
  `MCPServer` installs by default, which run in `ServerRunner`.

`client`
: one complete call through the official in-process `Client`, which adds the
  client session, the direct dispatcher pair, server params validation, server
  middleware and result validation to every scenario.

Servers, plans and clients are built before timing. Correctness is checked
after every warmup and after the timer stops for every timed batch. The
garbage collector is disabled only around timed samples and restored
afterward. Scenario order rotates on every sample so no scenario permanently
owns the first or last position.

## Run

From the repository root, after `uv sync`:

```bash
uv run python benchmarks/mcp_tool_invocation.py
uv run python benchmarks/mcp_tool_invocation.py \
  --iterations 1000 --samples 9 --warmups 2 --json
```

The JSON contract records raw elapsed samples, nanoseconds per call, minimum,
median, mean, maximum and sample standard deviation for both boundaries, plus
the rotating order, SDK and Agnara versions, sampling controls, both
measurement boundaries, Git state, Python/GIL/platform/processor/clock
metadata and median ratios to `direct_sdk`.

## Recorded baseline

Two consecutive runs were retained instead of selecting the more favorable
one:

```text
recorded at: 2026-09-05T03:58:57.240239+00:00 and 2026-09-05T03:59:25.259905+00:00
source base commit: ed87f520b833d7ccbb19a542d711dce3d626602f
dirty: true (the E7.9 benchmark under measurement is not yet committed)
command: uv run python benchmarks/mcp_tool_invocation.py --iterations 1000 --samples 9 --warmups 2 --json
platform: Windows 11 10.0.26200 (AMD64)
processor: Intel64 Family 6 Model 140 Stepping 1, GenuineIntel
logical CPU count: 8
Python: CPython 3.14.4
GIL enabled: true
timer: QueryPerformanceCounter(), 100 ns reported resolution
mcp 2.1.1, mcp-types 2.1.1, agnara 0.1.0a2, agnara-mcp 0.1.0a2
network / framing / concurrency: excluded
```

### Handler boundary

| Scenario | First median ns/call | Second median ns/call | Observed median range | Ratio range to direct SDK |
| --- | ---: | ---: | ---: | ---: |
| `direct_sdk` | 6,190 | 4,549 | 4,549–6,190 | 1.00x |
| `mcpserver_sync` | 216,272 | 154,693 | 154,693–216,272 | 34.01–34.94x |
| `mcpserver_async` | 31,610 | 22,855 | 22,855–31,610 | 5.02–5.11x |
| `agnara_mcp_sync` | 32,198 | 26,270 | 26,270–32,198 | 5.20–5.77x |
| `agnara_mcp_async` | 31,680 | 23,081 | 23,081–31,680 | 5.07–5.12x |

### Client boundary

| Scenario | First median ns/call | Second median ns/call | Observed median range | Ratio range to direct SDK |
| --- | ---: | ---: | ---: | ---: |
| `direct_sdk` | 186,800 | 222,648 | 186,800–222,648 | 1.00x |
| `mcpserver_sync` | 600,851 | 971,378 | 600,851–971,378 | 3.22–4.36x |
| `mcpserver_async` | 344,150 | 340,756 | 340,756–344,150 | 1.53–1.84x |
| `agnara_mcp_sync` | 288,711 | 301,552 | 288,711–301,552 | 1.35–1.55x |
| `agnara_mcp_async` | 286,413 | 279,765 | 279,765–286,413 | 1.26–1.53x |

## Reading these numbers

Dispersion is material. Sample standard deviation reached roughly 20–30% of
the median in several scenarios, the `direct_sdk` reference itself moved by
about 19% between runs at the client boundary, and ratios amplify that
movement. Nothing here is a portable constant or a regression threshold.

With that noise stated, three things are supported by the data:

1. At the handler boundary, `mcpserver_async`, `agnara_mcp_sync` and
   `agnara_mcp_async` overlap. Agnara's compiled dispatch, scope policy, input
   validation, DI scope and canonical projection cost about the same as
   `MCPServer`'s ergonomic tool path, at roughly 5x a hand-written handler
   that does none of it.
2. `mcpserver_sync` is an order of magnitude slower than every other scenario,
   and profiling attributes that to `anyio.to_thread.run_sync`. This is a
   worker-thread hop, not dispatch overhead, and it is a real cost for a
   synchronous tool.
3. At the client boundary the official client and dispatcher dominate every
   scenario, compressing the differences. Agnara's advantage over
   `mcpserver_async` there is within noise, and part of any remaining gap is
   the output validation Agnara does not yet give the client anything to do.

What the data does not support: a claim that Agnara is faster than FastMCP in
production, on another platform, under concurrency, over a network transport,
or once Agnara publishes and validates output schemas.

## Architectural interpretation

E7.9 asked whether invocation overhead justifies changing the adapter. It does
not. No hot path here is dominated by an Agnara abstraction that could be
removed without removing a documented guarantee, and no result approaches the
threshold `PERFORMANCE.md` sets for considering native acceleration. The
comparison's main actionable finding concerns the SDK's synchronous-tool
policy rather than Agnara's own code.

Revisit when output schema projection lands, when a network transport is
implemented, or when a concurrency benchmark exists — each changes the
measured path enough to invalidate this baseline.

## Sources

- https://pypi.org/project/mcp/2.1.1/
- https://github.com/modelcontextprotocol/python-sdk/tree/v2.1.1
- https://modelcontextprotocol.io/specification/2026-07-28/server/tools
