# ADR 0023: Structured Execution Telemetry Hooks

## Status

Accepted

## Context

The execution runtime (`invoke` and `invoke_result`) requires structured observability points so that metrics, traces, and logs can be generated for capability invocations. However, Agnara's core framework must not depend on OpenTelemetry or any specific observability SDK to remain lightweight and transport-neutral. Furthermore, dynamically scanning a global hook registry on every hot-path invocation introduces unnecessary overhead and violates predictability.

We need a mechanism to:
1. Wrap synchronous and asynchronous capability executions.
2. Provide immutable lifecycle events exactly once per invocation (start and terminal).
3. Identify terminal outcomes clearly (success, failure, timeout, cancellation) alongside monotonic execution durations.

## Decision

We will introduce a `TelemetryHook` protocol and attach immutable tuples of hooks directly to `ExecutionPlan` instances during compilation.

1. **Protocol-neutral Events**: Two frozen slotted dataclasses (`InvocationStartEvent` and `InvocationTerminalEvent`) will represent the lifecycle events. They will carry the `capability_id` and an optional `tracking_id` from the transport metadata.
2. **Immutable Hook Registration**: Hooks will be provided as an iterable to `ExecutionPlan.compile(..., hooks=...)` and stored as an immutable tuple. There will be no dynamic registry.
3. **Outcome Semantics**: The terminal event will classify the outcome as a literal string (`"success"`, `"failure"`, `"timeout"`, `"cancellation"`) and record the `duration_ns` using `time.monotonic_ns()`.
4. **Hook Isolation**: Hooks are synchronous, must not block, and their exceptions will be caught and silently ignored by the runtime so they cannot fail the actual capability execution.
5. **No Data Leakage**: Events will not contain capability parameters, return payloads, or exception structures. This avoids accidental PII leakage into observability pipelines and keeps the footprint small.

## Consequences

- The `ExecutionPlan` compiler must now be supplied with any desired telemetry hooks. Adapters will compile their plans with the necessary OpenTelemetry hooks later in EPIC 9.
- `invoke` now natively handles lifecycle emissions. Because `invoke_result` calls `invoke`, terminal events are emitted exactly once regardless of whether the caller requested ergonomic Python exceptions or canonical HTTP-friendly results.
- OpenTelemetry spans and context propagation are firmly relegated to an external provider package (`agnara-telemetry`), preserving the core's purity.
