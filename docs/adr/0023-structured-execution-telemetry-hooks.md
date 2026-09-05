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

1. **Protocol-neutral Events**: Two frozen slotted dataclasses (`InvocationStartEvent` and `InvocationTerminalEvent`) will represent the lifecycle events. They will carry the `capability_id` and an optional `tracking_id` from the invocation metadata.
2. **Immutable Hook Registration**: Hooks will be provided as an iterable to `ExecutionPlan.compile(..., hooks=...)` and stored as an immutable tuple. There will be no dynamic registry.
3. **Outcome Semantics**: The terminal event will classify the outcome as a literal string (`"success"`, `"failure"`, `"timeout"`, `"cancellation"`) and record the `duration_ns` using `time.monotonic_ns()`.
4. **Hook Isolation**: Hooks are synchronous, must not block, and their exceptions will be caught and silently ignored by the runtime so they cannot fail the actual capability execution.
5. **No Data Leakage**: Events will not contain capability parameters, return payloads, or exception structures. This avoids accidental PII leakage into observability pipelines and keeps the footprint small.

## Consequences

- The `ExecutionPlan` compiler must now be supplied with any desired telemetry hooks. Adapters will compile their plans with the necessary OpenTelemetry hooks later in EPIC 9.
- `invoke` now natively handles lifecycle emissions. Because `invoke_result` calls `invoke`, terminal events are emitted exactly once regardless of whether the caller requested ergonomic Python exceptions or canonical protocol-neutral results.
- OpenTelemetry spans and context propagation are firmly relegated to an external provider package (`agnara-telemetry`), preserving the core's purity.

## E9.1 implementation clarification (Issue #211)

E9.1 reuses this accepted port; it does not introduce another observer API.
`ExecutionPlan.__post_init__` now copies hooks to a tuple and validates both
callbacks, so direct construction has the same collection ownership as
`ExecutionPlan.compile`. Mutating the supplied list later cannot change the
callbacks registered for a compiled plan. Order and duplicate registrations
are preserved; each registration receives its own callback dispatch.

Each hook must expose callable `on_invocation_start` and
`on_invocation_terminal` attributes. Coroutine, asynchronous-generator and
synchronous-generator functions are rejected with `DefinitionError`, including
those supplied as a callable object's `__call__`. Such callbacks previously
produced unevaluated objects or silently lost telemetry. Diagnostics name the
hook index and callback without rendering the hook's state.

Validation does not call hooks and does not move reflection to invocation.
It is structural validation, not a proof of application code behavior: a
synchronous wrapper that secretly returns an awaitable still violates the
contract. Callbacks must accept one event and synchronously return `None`.
Ordinary callback `Exception`s remain silently ignored; `BaseException`
control signals are not suppressed. No promise is added that those signals
produce a balanced start/terminal pair.

Hook objects remain adapter-owned and may be shared by concurrent invocations.
Freezing the collection does not freeze or synchronize their state. Adapters
must provide their own synchronization or task-local state, avoid blocking
callbacks, and own exporter setup, flushing and shutdown. Hooks must not be
reconfigured while compiled plans use them. Caller-provided tracking IDs are
neither guaranteed unique nor safe storage keys for invocation state; do not
put secrets in them. Core does not create spans or own exporter resources.

`tests/unit/execution/test_telemetry_configuration.py` covers both construction
paths, invalid callback forms, source-list mutation, declaration order,
duck-typed synchronous hooks and the absence of callback execution during
validation. Existing lifecycle tests cover success, failure, timeout,
cancellation and ordinary hook failure isolation. OpenTelemetry integration,
span linking, semantic conventions and no-op cost evidence remain E9.2-E9.6.

## E9.3 invocation identity (Issue #219)

This decision said tracking IDs are not safe storage keys but left observers
with no key at all, which blocked spans. Both events now also carry a required
`invocation_id` that the runtime generates once per invocation and repeats on
the terminal event. It is unique per invocation, never derived from caller
metadata, and opaque: an in-process correlation key, not a business identifier.

The port shape is otherwise unchanged. Callbacks stay synchronous, exception
suppression is unchanged, and a hook that only reads events needs no change.
Because the field is required, code that constructed either event positionally
must supply it; this is a breaking change recorded in the changelog.

A hook that opens per-invocation state at start must release it in the terminal
callback keyed by that identity. The runtime suppresses an ordinary exception
from the start callback, so a terminal event can arrive for an invocation whose
start never completed; an observer must tolerate that rather than assume a
balanced pair. Recorded by ADR 0055, which also owns span semantics.
