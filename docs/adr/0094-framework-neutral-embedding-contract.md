# ADR 0094 — Framework-Neutral Embedding Contract

- Status: Accepted
- Date: 2026-09-15
- Tracking: GitHub Issue #420
- Initiative: I20
- Resolves: RFC 0008 (host-boundary questions only)
- Related: ADR 0003, ADR 0022, ADR 0026, ADR 0055, ADR 0068, ADR 0089, ADR 0091, ADR 0093

## Context

docs/INTEROPERABILITY.md requires standalone, hosted, embedded and side-by-side
operation. RFC 0008 correctly identified the ownership questions, but an
external host still had no accepted way to assemble and invoke the public
compiled runtime values.

A framework-specific facade would shape the kernel around the first host's
request object, lifecycle or error model. It would also make a provisional API
look stable before I9's explicit public-API decision.

## Decision

The stable architectural boundary is an explicit host-owned asynchronous
adapter over existing public, provisional core values. This ADR adds no Python
export and promotes no symbol to stable.

### D1 — One complete-result asynchronous invocation path

At startup, application code creates one Agnara application, freezes it with
Agnara.compile(), compiles its ExecutionPlan values, constructs one
DIContainer, and gives the matching frozen registry, plans and container to a
CapabilityRuntime. The host retains that runtime explicitly. It never locates
it through a module global, import hook or ambient request state.

For each call the host builds an Invocation and an ExecutionContext with the
same container, awaits CapabilityRuntime.invoke_result(context), and maps the
canonical Success or Failure at its own boundary. CancelledError is never
mapped to success or a canonical failure.

This is only an asynchronous, complete-result contract. A synchronous host
owns its async integration and must not create a nested event loop. Streaming
projection, delegated authority, cross-application composition, retries and
durable work are out of scope.

### D2 — Ownership is singular and explicit

| Concern | Owner | Rule |
| --- | --- | --- |
| Process, routing, middleware and request lifespan | Standalone/Agnara host: Agnara composition root; embedded/side-by-side: external host | The non-owner neither starts a second server nor mutates the other's route table. |
| Capability declaration, frozen snapshot, plans and semantics | Application/Agnara | Compile once before calls; never mutate the snapshot at runtime. |
| Per-call context, policy, validation, canonical result and invocation dependencies | Agnara runtime | Every host call uses the normal compiled path. |
| Native host request/session/transaction lifecycle | External host | Agnara never closes a host-owned resource. |
| Application-owned singleton providers | DIContainer owner | CapabilityRuntime.aclose() runs only after calls are drained. |
| Error representation, response and host logging | External host adapter | Map canonical outcomes outward; do not inject host error objects inward. |
| Host telemetry instrumentation | External host | It may surround the adapter call; it does not redefine capability lifecycle hooks. |

aclose() is a one-runtime shutdown operation, not process shutdown. A host
with more than one Agnara application closes each only after that runtime's
calls have drained; it never shares a mutable container merely because the
applications share a process.

### D3 — The bridge contains values, never host objects

The host may pass a declared capability id, schema-bound plain input, optional
opaque correlation label, non-extendable absolute monotonic deadline, a
Principal mapped from host-authenticated state, and application-defined
framework-neutral DI ports or immutable configuration.

Raw request/response/session, ORM transaction, connection, framework user,
middleware/task state, event loop, telemetry span/exporter, credential and host
exception objects must not enter Invocation.metadata, ExecutionContext.state,
a normal handler parameter or an Agnara DI binding. An application-defined port
may encapsulate host infrastructure outside the kernel, but the handler
receives the port contract, never the host object, and its declared owner
remains responsible for cleanup.

Principal mapping is a security boundary. It must not manufacture scopes,
confirmation evidence, delegation state, execution identities or idempotency
selectors from untrusted request data. Missing or invalid mapping becomes
AnonymousPrincipal, so scoped policy fails closed. Host authentication never
replaces Agnara policy evaluation.

### D4 — Reuse, concurrency and reentrancy are constrained

The frozen registry and ExecutionPlan values are immutable and shareable. One
live DIContainer/CapabilityRuntime belongs to one host event loop; concurrent
tasks on that loop may invoke it, but separate event loops and OS threads may
not share it. Singleton construction is serialized and invocation dependencies
remain per call.

The host awaits every invocation as structured work, propagates cancellation,
does not fire-and-forget runtime work, and does not call aclose() while a call
is active. Re-entrancy through CapabilityInvoker preserves ADR 0093's
same-snapshot, complete-result and policy rules; host re-entry creates no
second composition semantic.

### D5 — Four modes, one boundary

| Mode | Outer owner | Contract use |
| --- | --- | --- |
| Standalone | Agnara composition root | Compile and invoke with core alone. |
| Agnara host | Agnara composition root | Reach external infrastructure through application-defined ports. |
| Embedded Agnara | External host | A host route or task invokes the explicit runtime handle. |
| Side-by-side | External host | Native routes and the runtime handle share one lifespan without globals. |

### D6 — Framework-neutral conformance shape

Each mode supplies the same application-owned setup and call shape; only the
outer owner named in D5 changes:

```python
async def invoke_from_host(runtime, container, capability_id, payload, principal):
    context = ExecutionContext(
        Invocation(capability_id, payload, {}),
        container,
        principal=principal,
    )
    return await runtime.invoke_result(context)
```

Standalone calls this from its composition root. An Agnara-hosted application
uses the same call behind an application-owned infrastructure port. An embedded
host calls it from one native route or task. A side-by-side host calls it beside
native routes while sharing the host lifespan. The conformance fixture replaces
only the outer host harness; it does not import a host package into core tests.

## Consequences

- Starlette, FastAPI and Django fixtures can independently implement the same
  bridge without a framework import in core.
- This contract is enough to test ownership, mapping, cancellation, principal
  handling and cleanup; it does not claim concrete framework support.
- I9 still decides whether the named provisional symbols become stable for
  1.0.0. Version-pinned framework fixtures and a maintainer support decision
  remain necessary before the release interoperability gate can close.

## Alternatives rejected

### A framework-specific HostApp in core

Rejected: it would import a first framework's lifecycle and create an
unreviewed public API.

### Raw host request or transaction injection

Rejected: it leaks framework state into handlers and confuses cleanup and
policy ownership.

### One global runtime per process

Rejected: it prevents independent applications in one process and hides
event-loop ownership in mutable global state.

### Automatic retry for an idempotent capability

Rejected: idempotency deduplicates an explicitly scoped completed result; it
does not authorize retrying an effect. Retry remains host/application policy.

## Evidence and revisit

tests/architecture/test_embedding_contract.py checks the accepted contract,
all four modes, the absence of a new public export and the existing
framework-dependency boundary. It is contract evidence only: no concrete
framework fixture is exercised.

Revisit when a fixture cannot express a needed boundary, when I9 classifies the
public symbols for 1.0.0, or before adding streaming, delegation,
cross-application execution or a synchronous entry point.
