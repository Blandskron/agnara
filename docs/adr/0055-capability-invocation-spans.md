# ADR 0055 — Capability Invocation Spans over a Runtime Invocation Identity

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #219 (E9.3)

## Context

ADR 0023 defined two synchronous lifecycle events carrying `capability_id`, an
optional caller `tracking_id`, an outcome and a monotonic duration. E9.2 built
metrics on the terminal event alone, which needs no correlation. ADR 0054 then
recorded the blocker for spans explicitly: *"Correlating start and terminal
events to spans needs a separately reviewed execution-context contract; defer
it to E9.3/E9.4."*

A span is not a measurement. It must be opened at start and ended at the
matching terminal, so an observer needs to know which terminal belongs to which
start. Nothing in the event pair supported that:

- `tracking_id` is optional, so an observer cannot rely on it existing.
- It is caller-supplied, so two invocations may share one value, and on a
  remote transport its value is attacker-influenced.
- ADR 0023 already states it is *"neither guaranteed unique nor a safe storage
  key for invocation state"*.

Pairing by capability identity fails for concurrent or nested invocations of
the same capability. Pairing by arrival order fails as soon as two invocations
overlap, which is the normal case for an async runtime.

## Decision

### 1. Core supplies the identity

Both lifecycle events gain a required `invocation_id: str`. The runtime
generates it once per invocation, immediately before the start event, as
`uuid4().hex`, and repeats the same value on the terminal event.

The field is appended to each event rather than inserted, so existing
positional construction fails loudly with a missing-argument error rather than
silently binding a value to the wrong field.

Properties an observer may rely on:

- present on every emitted event, and equal across a start/terminal pair;
- distinct for every invocation, including nested, concurrent and sequential
  reuse of one compiled plan;
- never read from, derived from or equal to caller metadata;
- opaque. It is an in-process correlation key. Do not parse it, do not derive
  a trace ID from it, and do not treat it as a stable business identifier
  across processes.

Random generation was chosen over a process counter because a counter is
shared mutable state whose atomicity would rest on CPython implementation
detail, which AGENTS.md forbids relying on. The cost is one `uuid4()` per
invocation on a path that already performs policy evaluation, input validation
and dependency resolution. No performance claim is made here; measuring the
observer path is E9.6.

Core gains no OpenTelemetry dependency and no span, tracer or exporter
concept. `tests/architecture/test_package_boundaries.py` asserts that core
declares no name containing tracing vocabulary, so this identity cannot become
a foothold for the SDK's model migrating inward.

### 2. The adapter owns the span

`OpenTelemetryTracingHook(tracer)` in `agnara_telemetry` implements the same
structural hook port. The application supplies an OpenTelemetry API `Tracer`;
no global provider is read or installed.

| Element | Value |
| --- | --- |
| Span name | `str(capability_id)` |
| Kind | `INTERNAL` |
| Attributes | `agnara.capability.id`, `agnara.invocation.outcome` |

The start callback starts a span and attaches it to the OpenTelemetry context.
The terminal callback removes the entry, sets the outcome attribute and status,
detaches the context token and ends the span.

Status mapping is deliberate rather than mechanical:

| Outcome | Status | Reason |
| --- | --- | --- |
| `success` | `OK` | the capability completed |
| `failure` | `ERROR` | the capability raised |
| `timeout` | `ERROR` | the declared deadline was breached |
| `cancellation` | `UNSET` | the caller withdrew; the capability did not fail |
| unrecognized | `UNSET` | recorded as `unknown`, never as its raw value |

The status description carries the outcome word only. Exception text, argument
values, results, principals, transport fields and the `tracking_id` are never
attached, and no span events are recorded. The `invocation_id` itself is not
exported either: it pairs events in-process, and as an attribute it would be
unbounded cardinality on every span.

### 3. Nesting comes from context, not from bookkeeping

Attaching the span to the OpenTelemetry context is what makes a capability that
invokes another capability produce a child span, and it is why concurrent
invocations in sibling tasks do not adopt each other: each task runs with its
own copy of the context. Both callbacks of one invocation run in the same task,
with the terminal emitted from the runtime's `finally`, so the attach and
detach pair is properly nested.

That guarantee is the runtime's, not the hook's. Events delivered directly and
out of order fall outside it: every span still ends and exports, but
OpenTelemetry discards an out-of-order detach and the previous span is not
restored. `test_out_of_order_delivery_still_ends_every_span` pins that behavior
in an isolated context, because the damage otherwise leaks into unrelated work.
Do not hand-deliver interleaved events to this hook.

### 4. Bounded correlation state

The hook holds one dictionary from `invocation_id` to its open span and context
token, guarded by a `threading.Lock` held only across the dictionary operation,
never across span creation or export. The terminal callback removes the entry
before doing anything else, so a later failure cannot strand it, and the
runtime emits that callback from a `finally` block. The map is therefore
bounded by concurrently open invocations, not by total invocations.

Two degenerate cases are handled rather than assumed away. A terminal event
with no recorded start — the runtime suppressed the start callback, or the
hook was attached mid-flight — is ignored. Registering one hook twice on a
plan opens two spans for one identity; only the first is tracked, and the
duplicate is detached and ended immediately instead of overwriting the
tracked entry.

## Alternatives considered

**Reuse `tracking_id`.** Rejected for the reasons in Context; it would build
correlation on a value a remote caller controls.

**A monotonic process counter.** Cheaper than a UUID, but it is shared mutable
state whose thread-safety would depend on GIL behavior.

**A scope-shaped port** returning a context manager per invocation would suit
spans better than two callbacks. It also lets an observer wrap execution and
therefore suppress or delay it, which is a much larger security and lifecycle
change than E9.3 needs. The two-callback port is unchanged.

**Exporting `invocation_id` as a span attribute.** Rejected: unbounded
cardinality, and the span ID already identifies the span.

## Consequences

Adding a required field to two frozen public events is a breaking change for
code constructing them directly, which is recorded in the changelog under the
pre-`1.0` alpha policy. The runtime's own emission and every existing hook that
only reads events are unaffected.

Unreachable code at the end of `invoke` — four statements after a `try` block
whose every branch returns — was removed while adding the identity. It was
dead before this change and is not a behavior change.

## Scope

Transport span linking is E9.4: this ADR creates no remote parent, injects and
extracts no propagation headers, and makes no claim about a span produced by an
HTTP or MCP adapter. Semantic convention compatibility is E9.5: the span name
and both attributes are custom Agnara names and are not asserted to satisfy any
OpenTelemetry protocol or GenAI convention. No-op cost evidence is E9.6.

Proposed status does not claim maintainer architectural approval.

## Evidence

Only `agnara-telemetry` depends on `opentelemetry-api`; the SDK stays pinned to
1.44.0 in the development group for in-memory span exporter tests. No package
versions change.

- `tests/unit/execution/test_invocation_identity.py` — 15 core cases covering
  pairing, sequential distinctness over 200 invocations, independence from four
  `tracking_id` shapes, agreement across hooks on one plan, nesting, 50
  concurrent invocations, a suppressed start, every non-success outcome and
  frozen-event immutability.
- `tests/telemetry/test_tracing.py` — 30 real-SDK cases covering construction,
  the closed outcome and status vocabulary, redaction, runtime outcomes,
  parent/child nesting, 25 concurrent invocations, current-span restoration,
  released correlation state, duplicate registration, composition with the E9.2
  metrics hook and application-owned shutdown.
- `tests/architecture/test_package_boundaries.py` — API-only dependency,
  no SDK import, and the core tracing-vocabulary rule.

Primary sources checked on 2026-09-05:

- [Tracing API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [Python tracing API](https://opentelemetry-python.readthedocs.io/en/latest/api/trace.html)
- [Context API](https://opentelemetry.io/docs/specs/otel/context/)
- [Published API baseline](https://pypi.org/project/opentelemetry-api/1.44.0/)
- [Published SDK baseline](https://pypi.org/project/opentelemetry-sdk/1.44.0/)
