# Embed Agnara in FastAPI

An existing host can invoke Agnara capabilities from its native routes through
the public `CapabilityRuntime` boundary. The host owns authentication, routing,
responses and lifespan. Agnara evaluates capability policy, validates inputs
and output, resolves dependencies and returns a canonical outcome.

The complete source is [examples/fastapi_embedding.py](../examples/fastapi_embedding.py).
Its [tests](../tests/docs/test_fastapi_embedding_example.py) exercise the real
ASGI host and explicit lifespan without starting a network server. This guide
teaches the existing [ADR 0094 contract](adr/0094-framework-neutral-embedding-contract.md);
FastAPI remains an optional host dependency outside Agnara distributions.

## Run the example

Python >=3.14 is required. From the repository root:

```bash
uv sync
uv run python examples/fastapi_embedding.py
uv run pytest tests/docs/test_fastapi_embedding_example.py tests/integration/fastapi
```

The workspace pins FastAPI 0.141.1 for integration evidence. The runtime
imports used by the example are governed by [public-api.json](public-api.json).
An editable checkout's distribution version does not prove historical wheel
behavior; [release history](https://github.com/Blandskron/agnara/releases/tag/v1.0.3)
owns the published baseline. The host fixture does not establish a general
FastAPI support tier.

The requests produce these observable results:

| Request | Host status | Body |
| --- | --- | --- |
| Alice reads `/orders/A-1` | 200 | `{"order":"A-1","status":"shipped"}` |
| Bob has a valid credential but lacks `orders:read` | 403 | `{"error":"forbidden"}` |
| Unknown or missing credential | 401 | `{"detail":"unauthenticated"}` |
| Native `/health` route | 200 | `{"status":"ok"}` |

The token dictionary is demonstration data, not production credential
verification. Replace `authenticate` with the host's trusted verification
boundary. Never derive granted scopes from client headers or copy credentials
into invocation metadata, DI bindings or handler parameters.

## Compile once in the host lifespan

`build_application()` declares an `orders.summary` capability with the
`orders:read` scope and an explicit `dict[str, str]` output contract. Its
handler receives only `order_id`; it imports no FastAPI request or response type.

`compile_embedded()` includes that bounded context in one project, freezes the
capability registry, compiles a plan for each definition and constructs one
container and runtime over that exact snapshot. `build_host()` calls it inside
the asynchronous lifespan, before serving calls. The host retains this handle
in its closure instead of a process-global runtime.

Every native route invocation creates a fresh `Invocation` and
`ExecutionContext`, then awaits `runtime.invoke_result(context)`. Concurrent
tasks on the owning event loop may share the runtime and container. A runtime
must not be reused across event loops or OS threads. Do not call `asyncio.run`
inside a running host route.

## Map identity before calling the runtime

The host turns a verified credential into a `Principal` containing the identity
and granted scopes. Unknown credentials produce no principal, and this example
returns 401 before invoking Agnara. Bob's credential is accepted by the host,
but the compiled capability's scope policy refuses him before the handler runs.
Authentication and capability authorization are independent checks.

`correlate()` accepts an optional request label up to 128 characters using its
explicit token grammar. Invalid labels are dropped without failing an otherwise
valid request. This label is correlation data; it cannot select an execution,
grant authority, provide confirmation or deduplicate work. No request object,
bearer credential or arbitrary request metadata crosses the bridge.

## Map canonical outcomes at the host boundary

The host serializes `Success.value` into its own JSON response. The explicit
output contract validates that value before the host receives it. `Failure`
contains protocol-neutral code and redacted message; the host chooses its wire
format and status.

This small example maps every canonical failure to 403. Its route passes a
string to a simple, deterministic handler, so the demonstrated failure is
scope denial. A larger application must define mappings for invalid input,
timeout, conflict and internal failure separately. Use the canonical failure
code instead of interpreting handler exceptions or diagnostics. Cancellation
propagates and must not become a successful response.

## Close on the owning loop

The lifespan's `finally` block awaits `runtime.aclose()` and clears its runtime
and container handles. It runs for normal shutdown and exceptional lifespan
exit. The host must first drain or cancel and await active invocations; closing
a container while its calls are active violates the ownership contract.

The example awaits each ASGI request, and the concurrent test uses owned,
awaited work before lifespan exit. Tests check shutdown on the startup loop,
separate execution contexts and identities, denial before handler effects,
credential exclusion and malformed correlation rejection.

This bridge handles complete results. It adds no automatic mounted-child
lifespan, merged OpenAPI, retries, durable storage, synchronous bridge or
streaming projection. Those boundaries and the broader fixture inventory are
recorded in [INTEROPERABILITY.md](INTEROPERABILITY.md).
