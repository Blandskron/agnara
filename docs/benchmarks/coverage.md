# Benchmark Coverage and Gate Boundaries

This inventory separates release-gate evidence from comparative and exploratory
measurements.  A benchmark is not a release budget merely because it emits a
number.

| Benchmark | Engineering question | Timed boundary | Gate status |
| --- | --- | --- | --- |
| `runtime_paths.py` | Did final compiled core paths regress? | Registration/freeze and plan compilation at startup; warm core invocation and selected feature paths. | `docs/performance/budgets.json` gates the calibrated complete-invocation metrics. Stream phases, registration and embedding are recorded observations pending V1-40 calibration. |
| `runtime_invocation.py` | What does the bare warm compiled invocation cost? | One direct handler, `invoke`, and `invoke_result` over a precompiled plan. | Context only; its direct-handler ratio is duplicated as a coarse guard in `runtime_paths.py`. |
| `telemetry_overhead.py` | Does no-op telemetry remain guarded? | Precompiled invocation with and without registered hook work. | Context only; ADR 0058 owns the semantic guard. |
| `http_frameworks.py` | How do identical in-process ASGI exchanges compare? | One warm ASGI request, compiled routing, binding, invocation and JSON response; no server or network. | Comparison research only. Never a release gate or framework claim. |
| `mcp_tool_invocation.py` | How do equivalent MCP tool calls compare? | SDK server dispatch and canonical projection, with scenario rotation. | Comparison research only. Never a release gate or protocol conformance claim. |
| `frozen_value_type_memory.py` | What memory is retained by frozen value representations? | Object allocation/retention experiment. | Exploratory only. |

## Final-semantics coverage

`runtime_paths.py` records each timed operation's scope and validates its
result after every sample.  The scenarios cover cold/startup registration and
compile scaling, warm async invocation, one and ten DI dependencies, one and
three policies, execution identity, idempotency claim and reuse, depth-one and
depth-three same-snapshot composition, and the ADR 0094 host-to-runtime
embedding call.  It also separates stream opening, one consumer pull, normal
completion, and a complete 16-unit lifecycle.

The fixed fixtures intentionally avoid a combinatorial matrix: one scalar
payload, one async handler, one process/task and standard-library JSON only
where idempotency stores a result.  The JSON record declares those dimensions,
the absence of an ASGI server, timer properties, CPU/OS, Python build and GIL
state.  HTTP routing/serialization and MCP dispatch use their own explicit
in-process comparison boundaries; their outputs must not be used as competitor
or server-throughput gates.

V1-40 owns repeated calibration before adding limits for the new observations.
V1-41 owns intentional CI regression fail/pass evidence.  A missing threshold
is therefore visible as an observation, not silently treated as a passing
budget.
