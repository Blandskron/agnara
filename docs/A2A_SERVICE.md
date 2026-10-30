# Calling the provisional A2A service

This guide uses the **unreleased checkout** and the provisional exports in
[ADR 0099](adr/0099-a2a-provisional-public-surface.md). The published
`agnara-a2a==1.0.3` wheel has no runtime API and cannot run it. A local 1.0.3
version string alone does not identify the candidate implementation.

## Run the example

With Python >=3.14, from the repository root:

```bash
uv sync --locked
uv run python examples/a2a_service.py
```

The complete [source](../examples/a2a_service.py) uses the pinned official
`a2a-sdk[http-server]==1.3.0` client with HTTPX's in-process ASGI transport.
It opens no socket and contacts no external service. The first output lines are:

```text
protocol: 1.0
unauthenticated: 401
invalid_input: invalid_input
forged_dependency: invalid_input
denied: forbidden
valid: 30.0
handler_failure: internal_failure
recovered: 10.0
```

The final line records resource acquisition and shutdown. The deliberately
failing handler also emits a redacted server-side log; its private diagnostic
does not reach the caller.

## Declare once and compose explicitly

The business capability takes an integer quantity and an injected `Ledger`,
returns a price, requires `catalog:read`, and declares `output=int`. It imports
no protocol objects. The negative-quantity branch is an intentional exception
fixture for redaction, not an application error-handling recommendation.

At the composition root, `A2a(app, surface="agents")` declares a surface and
`a2a.skill(total, id=..., name=..., description=..., tags=...)` selects its
single capability. Freeze declarations with `app.compile()` and compile each
`ExecutionPlan` using the explicit `DIRegistry`; then call `build_a2a_app`
with `a2a.compile()`, those plans and the owned container. There is no implicit
handler discovery or dependency compilation inside the builder.

Supply explicit public `A2aAgentCard` metadata and a host-owned absolute URL.
The example's card is public at `/.well-known/agent-card.json`; its JSON-RPC
endpoint is `/`. Card visibility grants no permission to execute. Each surface
serves one capability, with no request-selected capability or task state.

## Authenticate before capability execution

The example host checks a fixed table of demonstration credentials and writes
its verified `Principal` into the ASGI scope. `resolve_principal` reads only
that trusted scope field. It does not infer authority from a message, skill,
metadata or arbitrary bearer string. Replace the toy table with the host's
real authentication boundary before deployment.

An unknown credential is refused with HTTP 401 and `WWW-Authenticate` before
the malformed body is parsed. A known principal without `catalog:read` is
authenticated but refused by kernel policy before dependencies or the handler
run. Invalid input and a forged `ledger` field also have no application effects.

## Observe outcomes and resource ownership

The official client sends success and recovery calls as `SendMessageRequest`
objects. Each reply is a fresh agent message with one JSON data part containing
`{"result": value}`. Protobuf's numeric binding can serialize integers as
`30.0`; this does not change the capability's `output=int` contract. Exact
integers outside the ADR 0098 safe range are not supported.

Raw JSON-RPC calls demonstrate error envelopes without depending on SDK
exception formatting. `invalid_input` uses code `-32602`; policy and handler
failures use `-32603`. Read the category from
`ErrorInfo.metadata.agnaraCode`, not from the JSON-RPC code alone. Unexpected
exceptions return the fixed message `Internal error`, without private text.
See [ADR 0098 D6](adr/0098-a2a-complete-result-projection.md#d6--failure-table).

The container, lifespan and clients are created, used and closed on one loop.
`Ledger` is invocation-owned, closing after successful and failing calls.
`Pool` is a singleton, closing only after the official client, HTTP session and
ASGI lifespan have ended. The small host drives lifespan through an owned
`TaskGroup`; HTTPX does not drive it automatically. `finally` closes the
container when client work raises or is cancelled. There is no unowned task.

## Real-loopback host evidence

The separate [network tests](../tests/a2a/test_a2a_network.py) drive a Uvicorn
0.52.4/h11 fixture over real TCP on `127.0.0.1`, using an OS-assigned port and
the official A2A client. Uvicorn is pinned as a development fixture, not an
Agnara package dependency. HTTPX ignores proxy environment variables for these
local connections. No external endpoint, TLS or production server is tested.

| Boundary | Asserted observation |
| --- | --- |
| Card and invocation | The card advertises the actual listener URL and revision `1.0`; the official client receives the compiled capability's result. |
| Input and authority | HTTP 401 precedes parsing; malformed JSON, invalid input and a principal without the required scope have no dependency/handler effects. |
| Deadline and recovery | A waiting handler is cancelled at its kernel deadline, closes its invocation resource and maps to `timeout`; a subsequent call succeeds. |
| Peer closes mid-body | The admission gate receives `http.disconnect` and exits without acquiring application resources. |
| Peer closes after handler entry | Uvicorn does not cancel the request task automatically. The kernel deadline still cancels the handler and releases its invocation resource; the SDK constructs a timeout reply that the disconnected client cannot receive. |
| Graceful shutdown | The listener stops accepting connections, the active request completes, and invocation resources close before the host closes its singleton/container and lifespan. Server tasks and listener are joined/closed on the owning loop. |

The post-entry disconnect test waits for actual handler entry before closing a
real client socket. It observes a canonical timeout response at the ASGI send
boundary and provider teardown, rather than treating a closed client socket as
proof of task cancellation. The fixture does not add a disconnect watcher or
change adapter behavior. A host that needs cancellation immediately on peer
disconnect requires a separately designed policy that owns and joins that work.
The deadline remains cooperative; it does not roll back completed effects or
interrupt a blocking synchronous handler.

## Verification and limits

```bash
uv run pytest tests/docs/test_a2a_service_example.py tests/a2a
uv run pytest tests/a2a/test_a2a_network.py
uv run pytest tests/release/test_integrated_dogfooding.py
uv run python scripts/check_public_imports.py examples/a2a_service.py docs/A2A_SERVICE.md
```

The installed-artifact gate builds all seven candidate wheels, installs them
outside the checkout, copies the exact example, and runs the
[consumer](../tests/reference_apps/a2a_guide.py) under Python `-I`. It checks
wire values, failure categories, redaction, fresh message IDs, absence of
effects on refusal, and the complete cleanup sequence. The existing required
Linux/macOS/Windows test matrix runs that gate; it does not install a public
index substitute for a candidate Agnara wheel.

The runnable example and installed-wheel consumer remain in-process evidence;
the network suite separately measures the pinned Uvicorn/h11 fixture above.
Neither proves a production server lifecycle, immediate cancellation on
disconnect or support for arbitrary hosts. Tasks, streaming, push notifications,
extended or signed cards, other bindings and revisions, and confirmation-required capabilities remain
outside this profile. Exports stay provisional and maturity stays
`EXPERIMENTAL`; this guide does not promote protocol support.
