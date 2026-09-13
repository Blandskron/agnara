# Serving Capabilities over HTTP

How an application exposes Agnara capabilities over HTTP, using only public
API. Every import on this page is one an application may write; nothing here
reaches into an underscore-prefixed module, and
`tests/architecture/test_public_http_surface.py` fails if this page ever does.

`docs/API_DESIGN.md` owns the intended shape of the API and
`docs/PUBLIC_API.md` owns its stability. This page owns the supported path and
its limits.

## The whole public surface

Seven names, from `agnara_http`:

| Name | What it is |
| --- | --- |
| `Http` | Declare which capabilities one named HTTP surface exposes, and compile it. `get`, `post`, `put`, `patch`, `delete` and `route` project a complete result; `sse` projects a stream. |
| `HttpApplication` | The compiled result: an immutable ASGI 3 application. |
| `Binding` | Read one capability input from one place in the request. |
| `BindingSource` | Which place: `PATH`, `QUERY`, `HEADER`, `BODY`, `COOKIE`, `FORM`, `UPLOAD`. |
| `OpenApiInfo` | OpenAPI document metadata. |
| `OpenApiOperation` | The per-operation decision to publish, and its metadata. |
| `HttpDefinitionError` | One composition mistake, raised at startup. |

Everything else in `agnara_http` is underscore-prefixed and carries no
compatibility promise. If you find yourself needing one, that is a missing
public API and worth an issue — it is exactly the kind of finding the baseline exists to
surface.

All seven are `provisional`: deliberate entry points, with no compatibility
promise before `1.0.0`.

## A complete application

```python
import asyncio
from typing import Any

from agnara import Agnara
from agnara.core.di import DIRegistry, Scope, provider
from agnara_http import Binding, BindingSource, Http, OpenApiInfo, OpenApiOperation


class Ledger:
    def record(self, sku: str) -> str:
        return f"recorded {sku}"


@provider(scope=Scope.SINGLETON)
def provide_ledger() -> Ledger:
    return Ledger()


dependencies = DIRegistry()
dependencies.bind(Ledger, provide_ledger)

app = Agnara("shop")


@app.capability(description="Read one order.")
def show(order_id: str, verbose: bool = False) -> dict[str, Any]:
    return {"id": order_id, "verbose": verbose}


@app.capability(description="Create an order.")
def create(order: dict[str, Any], ledger: Ledger) -> dict[str, Any]:
    return {"sku": order["sku"], "note": ledger.record(str(order["sku"]))}


http = Http("public")
http.get(
    "/orders/{order_id}",
    show,
    Binding("order_id", BindingSource.PATH),
    Binding("verbose", BindingSource.QUERY),
    openapi=OpenApiOperation(summary="Show an order", publish_description=True),
)
http.post(
    "/orders",
    create,
    Binding("order", BindingSource.BODY),
    openapi=OpenApiOperation(summary="Create an order"),
)

asgi = http.compile(
    app.compile(),
    dependencies=dependencies,
    openapi=OpenApiInfo("Shop API", "1.0.0"),
    openapi_path="/openapi.json",
)
```

`asgi` is an ASGI 3 application. Hand it to any ASGI server:

```bash
uvicorn app:asgi
```

Being ASGI is a boundary, not an integration. Agnara speaks ASGI 3; supported
integration with a specific framework — FastAPI, Django, Starlette — belongs to
`1.0.0` and is not promised here (ADR 0068).

## Who owns what

The lifecycle is the application's, and there is no hidden global state. Two
`Http` builders in one process share nothing.

| Step | Owner | Call |
| --- | --- | --- |
| Create the application | you | `Agnara("shop")` |
| Declare capabilities | you | `@app.capability` |
| Freeze capabilities | you | `app.compile()` |
| Declare routes | you | `http.get(...)`, `http.post(...)` |
| Compile and freeze the surface | you | `http.compile(...)` |
| Startup and shutdown | you, through `lifecycle` | ASGI `lifespan` |
| Serve a request | the ASGI server | `asgi(scope, receive, send)` |

`http.compile()` is the startup step. Routes are parsed, collisions detected,
capabilities resolved, execution plans compiled and bindings validated, and the
result frozen (ADR 0005). A request then costs a trie lookup, a binding pass,
one invocation and one serialization.

The builder is single-use: after `compile()`, a further `http.get(...)` raises
rather than being silently dropped.

### Startup and shutdown

```python
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifecycle():
    pool = await open_pool()
    try:
        yield
    finally:
        await pool.close()


asgi = http.compile(app.compile(), dependencies=dependencies, lifecycle=lifecycle)
```

Startup enters the context manager, shutdown exits it. It cannot hand a value
back on purpose: application state belongs in dependency providers, which every
transport can reach, rather than in something only HTTP knows about.

The HTTP surface owns its DI container. ASGI lifespan shutdown closes singleton
provider resources before exiting the application lifecycle. Lifespan also runs
without a callback, so dependency cleanup does not require a custom hook. Keep
lifespan enabled on the ASGI server; requests must be drained before shutdown.
Each compiled surface belongs to one worker event loop.

## Bindings are explicit

Agnara does not infer that `{order_id}` in a path fills an input called
`order_id` (ADR 0026). Renaming a capability parameter should fail at startup,
not become a confusing validation error on the first request:

```
HttpDefinitionError: required input 'order_id' has no HTTP binding
```

`wire_name` renames an input on the wire, so a capability stays unaware that
HTTP exists:

```python
http.get("/me", show, Binding("account_id", BindingSource.HEADER, wire_name="x-account-id"))
```

Supported JSON body annotations today are standard-library dataclasses,
`dict[str, T]`, `list[T]`, primitives, tuples, unions, `Literal` and `Enum`.
Dataclasses are materialized recursively at this HTTP boundary before the
shared strict validation path runs (ADR 0075).

## Cookies, forms and uploads

ADR 0072 fixes what the baseline owns of the request surface. Three sources join
the four above, and they are the difference between "serves JSON" and "serves
an ordinary web application".

### A session cookie

```python
http.get("/profile", profile, Binding("session", BindingSource.COOKIE, wire_name="sid"))
```

One RFC 6265 pair, read by name, validated like any other scalar. Cookie names
are **case-sensitive**, unlike headers. A value is opaque text: percent,
base64 and quoted forms arrive exactly as sent, because guessing an encoding
would corrupt a value your capability is about to validate.

A cookie pair your application never set, whose name is not an HTTP token, is
skipped rather than failing the request. A repeated cookie *is* refused, like
any repeated scalar.

Sessions are yours: a cookie binding plus your own store. Agnara ships no
session framework.

### An HTML form

```python
http.post(
    "/sessions",
    sign_in,
    Binding("email", BindingSource.FORM),
    Binding("password", BindingSource.FORM),
    Binding("remember", BindingSource.FORM),
)
```

One declaration reads **both** `application/x-www-form-urlencoded` and
`multipart/form-data`, because you asked for a field and an HTML form picks
the encoding from its `enctype`. Fields are scalars and are type-checked;
`+` decodes to a space; a repeated field is refused.

### A file upload

```python
http.post(
    "/avatar",
    store,
    Binding("caption", BindingSource.FORM),
    Binding("avatar", BindingSource.UPLOAD, wire_name="file"),
    max_body_bytes=4 * 1024 * 1024,
    max_parts=8,
)


@app.capability
def store(caption: str, avatar: bytes) -> dict[str, Any]: ...
```

An upload binds to **`bytes`**, and the input must be annotated `bytes` — the
compiler refuses anything else, because decoding arbitrary uploaded bytes as
text fails on the first PNG.

What you should know before using it:

- **It is buffered in memory**, bounded by `max_body_bytes` (1 MiB by
  default). A route that raises the limit to 100 MB will hold 100 MB per
  concurrent request. That is your decision; request bodies are not streamed.
- **Nothing touches the filesystem.** There is no temporary file, so there is
  nothing to leak and nothing to clean up on cancellation or error. The bytes
  are owned by the invocation and released with it.
- **The client filename is not exposed.** It is attacker-controlled, and every
  safe use of it generates a name anyway. If you need an extension, ask for it
  as a form field. Exposing a filename needs the upload value type ADR 0072
  defers.
- **`max_parts` bounds the part count** (64 by default), separately from
  total size, because a small body can still carry thousands of empty parts.
- **One file per part name.** Several files need the collection binding
  ADR 0026 deferred.

### One request has one body

`BODY`, `FORM` and `UPLOAD` all read the request body. Combining `BODY` with
either of the others is refused at compile time — one request has one body and
the adapter will not guess. `FORM` and `UPLOAD` combine freely, which is what
an upload form posts.

A route with an upload accepts `multipart/form-data` only; a route with fields
alone accepts either encoding. The OpenAPI document advertises exactly that.

## Streaming with server-sent events

A capability declared `streaming=True` yields units instead of returning one
value, so it has no complete JSON representation and an ordinary `get` refuses
it. `Http.sse` is the one supported projection (ADR 0085):

```python
from collections.abc import AsyncIterator

from agnara import Agnara
from agnara_http import Binding, BindingSource, Http

app = Agnara("reports")


@app.capability(streaming=True, output=dict[str, int])
async def rows(report_id: int) -> AsyncIterator[dict[str, int]]:
    for line in range(report_id, report_id + 3):
        yield {"line": line}


http = Http()
http.sse("/reports/{report_id}", rows, Binding("report_id", BindingSource.PATH))
asgi = http.compile(app.compile())
```

A browser reads it with no Agnara vocabulary at all, because each unit is a
standard unnamed `message` event carrying one compact JSON value:

```text
200
content-type: text/event-stream; charset=utf-8
cache-control: no-store

data: {"line":7}

data: {"line":8}

data: {"line":9}

event: agnara.terminal
data: {"outcome":"completed","units":3}
```

**The response starts late, on purpose.** Policy, binding, validation,
dependency construction and the *first* pull all happen before the `200`. A
failure there has exposed nothing, so it is still an ordinary RFC 9457 problem
response with the status the table above gives it — a denied policy is `403`,
an expired deadline is `504`, a raised handler is a redacted `500`. An empty
producer is a success, not a failure: the response starts and ends with
`units: 0`.

**The end is stated, not inferred.** A closed connection cannot tell
exhaustion from failure, so every started response ends with one
`agnara.terminal` event. `outcome` is the core `StreamTerminal` value and
`units` is exactly how many data events were sent. A failure *after* output
adds a `problem` member carrying the same redacted problem document the
complete boundary would have produced:

```text
data: {"line":7}

event: agnara.terminal
data: {"outcome":"interrupted","problem":{...,"status":500},"units":1}
```

That is the whole point of the terminal event: a client that received one row
is never told the invocation produced nothing.

**Demand is the client's.** One pull, one encode, one awaited send, in that
order. A slow reader slows the producer, and the adapter holds at most one
encoded event — there is no queue anywhere. When the peer disconnects, the
producer is cancelled and its `finally` runs before the request returns; no
terminal event is promised to a connection that has gone.

What an SSE route deliberately does not do:

- **No request body.** `BODY`, `FORM` and `UPLOAD` bindings are refused: a
  browser `EventSource` issues a `GET`, and this projection supplies no
  request-body streaming contract. Path, query, header and cookie all work.
- **No `HEAD`.** It answers `405`, and `Allow` says `GET` only. Consuming a
  one-shot producer to discard every unit is not a useful answer.
- **No OpenAPI operation.** `sse` takes no `OpenApiOperation` and the route is
  absent from the document. There is no reviewed response schema for arbitrary
  stream units or for the terminal event, and inventing one would be a promise
  nobody reviewed (ADR 0085 D6).
- **No replay.** No `id` or `retry` field is sent and `Last-Event-ID` carries
  no meaning. A reconnecting client starts a new, ordinary invocation, with
  every policy and effect rule applied again.

`max_event_bytes` bounds one encoded event and defaults to the 1 MiB used for
request bodies. A larger unit fails the response rather than being truncated:
the operator gets a diagnostic naming the size, never the value.

This is deliberately the adapter's only per-unit resource limit. Connection
admission, concurrent connection counts, idle/read/write timeouts, TLS,
reverse-proxy buffering and process memory ceilings belong to the ASGI server
or reverse proxy that owns those resources. Configure them there; neither the
kernel nor `Http.sse` fabricates server policy.

## OpenAPI

`OpenApiInfo` supplies document metadata; `OpenApiOperation` on a route is the
decision to publish that operation at all.

```python
document = asgi.openapi()   # a dict, deterministic for one compiled surface
```

An exposure declared without an `OpenApiOperation` is served and appears
nowhere in the document — no path, no identifier, no description, no tag, no
schema fragment (ADR 0035). Publication is opt-in so that a deployment which
has not decided what to publish publishes nothing.

`openapi_path` serves the document. There is no default path: publishing an API
description is a deliberate act.

The request surface projects truthfully. A cookie is `in: cookie`. Form fields
and uploads are properties of one `requestBody` object with
`additionalProperties: false` — they are a body, not parameters — an upload is
`{"type": "string", "format": "binary"}`, and `encoding` carries the part's
content type as RFC 7578 requires. The advertised media types are the ones the
route accepts and no others.

`publish_description` is separate from `summary` because a capability docstring
is written for developers reading the code and may say more than a public
document should.

## Failures

Capability failures become RFC 9457 problem documents with
`content-type: application/problem+json`. The `code` member is the stable
machine-readable discriminator.

| Situation | Status | `code` |
| --- | --- | --- |
| No route matches | 404 | `not_found` |
| Route matches, method does not | 405 | — (`Allow` header) |
| Query, header or body cannot be decoded | 400 | `invalid_input` (`details.location`) |
| Value fails its compiled schema | 400 | `invalid_input` (`details.path`) |
| Body exceeds the limit | 413 | `content_too_large` |
| Multipart carries more than `max_parts` | 413 | `content_too_large` |
| Malformed multipart body or part | 400 | `invalid_input` |
| Form field is not valid UTF-8 | 400 | `invalid_input` (`details.location`) |
| A policy denies the invocation | 403 | `forbidden` |
| Deadline exceeded | 504 | `timeout` |
| Handler raised | 500 | `internal_failure` (message redacted) |

Decoded JSON is materialized after policy and before strict validation. This
is why a nested dataclass error uses canonical `details.path` beginning with
the capability input name rather than transport `details.location`. Direct
Python invocation remains strict. See ADR 0077 and
`CROSS_SURFACE_CONFORMANCE.md`.

Baseline capability dispatch has no HTTP authentication bridge and runs as
anonymous. Because declared scopes compile into the common plan, a scoped HTTP
capability fails closed with `403`; discovery visibility is not authorization.

`type` is `about:blank` unless you pass `problem_base_uri`, because Agnara does
not invent a documentation origin for your errors.

### Composition mistakes

`HttpDefinitionError` covers a duplicate route, an input with no binding or an
unsupported one, a declaration after compilation, and a surface that cannot be
projected into OpenAPI truthfully. It subclasses `DefinitionError`, so
`except AgnaraError` already covers it, and the adapter's own diagnostic stays
on `__cause__`.

A capability that is not declared on the registry you pass to `compile()`
raises `DefinitionError` unchanged: that is a capability mistake, not an HTTP
one.

## Composing with other transports

`HttpApplication.exposures` contributes to the project-wide exposure registry,
so one capability reachable over HTTP and MCP has one answer to "where is this
reachable?" (ADR 0070):

```python
from agnara.exposure import compile_exposures
from agnara.introspection import describe_app, snapshot

capabilities = app.compile()
asgi = http.compile(capabilities, dependencies=dependencies)
exposures = compile_exposures(capabilities, [asgi.exposures, mcp.compile_surface()])

document = snapshot([describe_app(app, asgi.plans, exposures=exposures)])
```

`asgi.plans` carries one compiled plan per capability *this surface exposes*,
so you need not compile them again. `describe_app` wants a plan for every
declared capability, so an application with capabilities HTTP does not expose
must compile those itself and pass the combined set.

## Baseline limitations

Stated plainly, because a guide that omits its limits is how a framework earns
distrust.

**Not exposed publicly, though implemented internally.** The documentation UI
providers (Swagger UI, ReDoc, Scalar), the read-only Agnara **Explorer** and
the authorized introspection **discovery** endpoint. These are not merely
unexported: the publication planner compiles placeholder routes and no code
path in the product renders a provider, so publishing an API for them would
publish an API for something that does not yet work end to end. Their
configuration is also security-sensitive — content security policy, asset
policy, principal resolution, redaction — and deserves its own review.

**Not implemented, and where to put it instead.** ADR 0072 classifies every
deferred request feature rather than leaving it implicit.

| Deferred | Why, and what to do in the baseline |
| --- | --- |
| Multiple files, repeated form fields | Both need a collection binding, which ADR 0026 deferred deliberately and which decides how a list arrives through *every* transport. Use distinct part names. |
| Client filename, per-part content type | Both need a public upload value type, and that is a core-visible schema shape MCP and introspection project too. Ask for a filename as a form field if you need one. |
| Streaming request bodies, large uploads | Needs the streaming model, I2, `0.1.0a9`. Until then an upload is bounded `bytes`. |
| **WebSocket**s, SSE replay and `Last-Event-ID` | I2, after `1.0.0`. The ASGI boundary handles no `websocket` scope, and resumption waits for the operational identity I3 must decide. Streaming *responses* are implemented: see `Http.sse` above. |
| CORS, compression, trusted hosts, proxy header trust | Put them in the reverse proxy or ASGI server in front of the application, or wrap the `HttpApplication` in any third-party ASGI middleware — it is an ASGI 3 callable, so they compose. |
| Static files | A web server or CDN. Agnara serves capabilities. |
| Middleware / interceptor hook | Deliberately absent. `docs/INITIATIVES.md` states why: "middleware in most frameworks is where transport types leak into application code, and Agnara must not reproduce that". Wrapping from outside, at the ASGI layer, keeps transport concerns where they belong. |
| Sessions | A cookie binding plus your own store. |
| Content negotiation, conditional and range requests | A response-model question, not a request one. Needs an RFC. |

**Dataclass bodies.** A JSON object bound to a standard-library dataclass is
materialized recursively before core validation, including nested dataclasses,
lists, dictionaries, tuples, unions and JSON-valued enums. Unknown fields and
missing required fields fail at the HTTP boundary. Direct core invocation
remains strict: only the transport that knows it received JSON performs this
conversion (ADR 0075, [issue #296](https://github.com/Blandskron/agnara/issues/296)).

**No authentication.** Every HTTP invocation runs as the anonymous principal,
so a capability carrying a `ScopePolicy` always answers `403`. Nothing here can
produce a `401`. Authentication integration is part of the security program
(I10, `1.0.0`).

**Publication-ready, not published.** Only the `agnara` core distribution is
uploaded today, so `agnara-http` must currently be installed from a locally
built wheel. ADR 0073 and
[issue #291](https://github.com/Blandskron/agnara/issues/291) make the tagged
workflow ready to publish the synchronized set; they do not perform a release.

**No compatibility promise.** Every name here is `provisional`. The path to `1.0.0`
may change any of them; `docs/PUBLIC_API.md` records the policy and ADR 0021
requires a changelog entry and migration guidance for a break.
