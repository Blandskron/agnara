# Embed Agnara in Starlette

Native Starlette routes can await a compiled `CapabilityRuntime` without
mounting a second ASGI application. Starlette owns authentication, requests,
responses and lifespan; Agnara owns capability policies, input/output
validation, dependency resolution and canonical outcomes.

Run [examples/starlette_embedding.py](../examples/starlette_embedding.py)
from the repository root with Python >=3.14:

```bash
uv sync
uv run python examples/starlette_embedding.py
uv run pytest tests/docs/test_starlette_embedding_example.py tests/integration/starlette
```

The workspace's optional Starlette fixture is pinned to 1.6.0. It is not a core
dependency or a general integration support tier. The example uses the existing
1.0.3 public API; checkout version strings do not prove published wheel behavior.
See the [public manifest](public-api.json), [embedding contract](adr/0094-framework-neutral-embedding-contract.md)
and [interoperability limits](INTEROPERABILITY.md).

## Native host boundary

The native `/health` route returns `{"status":"ok"}` without invoking Agnara.
`POST /orders` accepts an object such as `{"order_id":7}`. Its handler receives
an integer and an application `Audit` port, never a Starlette request or bearer
credential. An explicit `dict[str, int]` output contract validates success
before the host creates a JSON response.

`authenticate()` recognizes demonstration bearer tokens. Alice receives
`orders:read`; Bob is authenticated without that scope. Unknown credentials,
missing credentials and other schemes yield 401 at the host boundary. Replace
this token dictionary with trusted production verification; clients must never
choose their granted scopes or confirmation evidence.

| Case | Host status | Error or value |
| --- | --- | --- |
| Alice submits an integer | 200 | `{"order_id":7}` |
| Bob submits an object | 403 | `forbidden` |
| Missing/unknown credential | 401 | `unauthenticated` |
| Malformed JSON or non-object body | 400 | `malformed_json` or `object_required` |
| Missing/string `order_id` | 422 | `invalid_input` |
| Handler failure | 500 | `internal_failure` |

The host decodes JSON and rejects non-object bodies. Agnara validates the plain
payload against the compiled schema. The scope policy runs before input
validation, dependency acquisition and handler effects; Bob's malformed
capability input still yields a policy refusal. Credentials and raw request
metadata never enter `Invocation` or DI. This small in-process fixture does
not configure network request-size limits or deployment middleware.

## Lifespan and resources

`build_host()` retains a `State` handle in its composition closure. The async
lifespan declares and freezes capabilities, binds the application audit port,
compiles execution plans and constructs the live container/runtime on its loop.
Each route call creates a fresh invocation/context over that container.

The audit provider is an async singleton generator. The runtime closes it at
lifespan exit, then the host clears its runtime/container handles. The audit is
an in-memory application fixture, not durable storage or a transaction API.
Its events observe loop identity in host state; no event loop is injected into
a business handler.

Await each call, or use owned concurrent work such as `asyncio.TaskGroup`.
Drain calls, or cancel and await them, before runtime shutdown. Never share a
live container/runtime across loops or OS threads, and never nest `asyncio.run`
inside a route. Cancellation propagates instead of becoming an HTTP success
or canonical failure. The lifespan's `finally` closes resources on normal and
exceptional host exit.

## Canonical results and evidence

`failure_response()` maps forbidden/input/timeout/conflict outcomes to
403/422/504/409; other outcomes use the example's 500 fallback. It publishes only
the canonical code, never failure details or private diagnostics. These are
application-owned mappings for this example, not framework HTTP semantics or
a complete mapping for every policy interaction. Extend the mapping explicitly
when adding capabilities with other outcomes.

The [example tests](../tests/docs/test_starlette_embedding_example.py) drive
real ASGI calls without a network server. They check refusal before port/handler
effects, native route independence, overlapping principal/context isolation,
same-loop cleanup, propagated cancellation, redacted handler failure and an
exceptional host exit. The demonstration prints the success/refusal cases and
cleanup; concurrency and cancellation are exercised by those tests.

This is the existing complete-result bridge. It adds no automatic mounted-child
lifespan, merged OpenAPI, retry, streaming projection, ORM adapter or durable
work. Starlette remains responsible for its native middleware and deployment.
