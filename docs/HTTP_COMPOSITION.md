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
| `Http` | Declare which capabilities one named HTTP surface exposes, and compile it. |
| `HttpApplication` | The compiled result: an immutable ASGI 3 application. |
| `Binding` | Read one capability input from one place in the request. |
| `BindingSource` | Which place: `PATH`, `QUERY`, `HEADER`, `BODY`. |
| `OpenApiInfo` | OpenAPI document metadata. |
| `OpenApiOperation` | The per-operation decision to publish, and its metadata. |
| `HttpDefinitionError` | One composition mistake, raised at startup. |

Everything else in `agnara_http` is underscore-prefixed and carries no
compatibility promise. If you find yourself needing one, that is a missing
public API and worth an issue — it is exactly the finding `0.1.0a4` exists to
surface.

All seven are `provisional`: deliberate entry points, with no compatibility
promise during the alpha line.

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
`0.1.0b1` and is not promised here (ADR 0068).

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

Without a `lifecycle`, a `lifespan` scope raises. That is how an ASGI
application states it has no lifespan protocol, and a server running
`lifespan="auto"` handles it.

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

Supported body annotations today are `dict[str, Any]`, `list[T]`, primitives,
tuples, unions, `Literal` and `Enum`. **A dataclass-typed body does not work**
— see Limitations.

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
| A policy denies the invocation | 403 | `forbidden` |
| Deadline exceeded | 504 | `timeout` |
| Handler raised | 500 | `internal_failure` (message redacted) |

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

## Limitations of `0.1.0a4`

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

**Not implemented.** Cookies, form bodies, multipart and file uploads
(initiative I7). Streaming, server-sent events and **WebSocket**s (I2,
`0.1.0a5`). Middleware and interceptors, CORS, compression, static files, proxy
headers and trusted hosts. Content negotiation, conditional and range requests.

**Known defect.** A dataclass-typed request body publishes a correct JSON
Schema and then rejects every request that matches it, because the schema port
validates without coercing. Tracked as
[issue #296](https://github.com/Blandskron/agnara/issues/296); use
`dict[str, Any]` until it is decided.

**No authentication.** Every HTTP invocation runs as the anonymous principal,
so a capability carrying a `ScopePolicy` always answers `403`. Nothing here can
produce a `401`. Authentication integration is part of the security program
(I10, `0.1.0b1`).

**Not published to PyPI.** Only the `agnara` core distribution is uploaded, so
`agnara-http` must currently be installed from a locally built wheel. Tracked
as [issue #291](https://github.com/Blandskron/agnara/issues/291).

**No compatibility promise.** Every name here is `provisional`. The alpha line
may change any of them; `docs/PUBLIC_API.md` records the policy and ADR 0021
requires a changelog entry and migration guidance for a break.
