# Agnara in Django async views

A Django async view can await the public complete-result `CapabilityRuntime`
with plain inputs and a host-verified `Principal`. Django owns requests,
responses and authentication. Agnara evaluates capability policy, validates
contracts and owns the dependencies created by its container.

Run [examples/django_embedding.py](../examples/django_embedding.py) with
Python >=3.14 from the repository root:

```bash
uv sync
uv run python examples/django_embedding.py
uv run pytest tests/docs/test_django_embedding_example.py tests/integration/django
```

The existing optional fixture pins Django 6.1.1; Django is not an Agnara core
dependency or a general integration support tier. The program uses the existing
1.0.3 public API. An editable checkout's version does not prove published wheel
behavior. See the [public manifest](public-api.json) and the
[embedding contract](adr/0094-framework-neutral-embedding-contract.md).

## What the program exercises

`drive()` creates a Django `ASGIRequest` with `AsyncRequestFactory` and awaits
the corresponding native view. This exercises view input/response handling,
not an ASGI server, URL resolver, middleware, authentication backend, sessions
or CSRF enforcement. Django's [request factory documentation](https://docs.djangoproject.com/en/6.1/topics/testing/advanced/#asyncrequestfactory)
describes this testing boundary. The factory methods are synchronous; the
views themselves are async.

`configure_demo()` initializes minimal standalone Django settings only when
settings are unconfigured. Importing the example does not configure settings
or construct a runtime. Existing Django projects retain their own settings and
initialization. The script is a fixture, not a Django deployment recipe.

`Host.health()` represents a native GET `/health` view and returns
`{"status":"ok"}` without invoking Agnara. `Host.summary()` represents a POST
`/orders` view. Its capability receives `order_id: int` and an application
`Audit` port, never a Django request, user, session, credential or ORM object.
An explicit `dict[str, int]` output contract validates the returned value.

| Input | Status | Value or error |
| --- | --- | --- |
| Alice sends `{"order_id":7}` | 200 | `{"order_id":7}` |
| Bob sends an object | 403 | `forbidden` |
| Missing/unknown bearer credential | 401 | `unauthenticated` |
| Empty, malformed or invalid-encoding JSON | 400 | `malformed_json` |
| Non-object JSON | 400 | `object_required` |
| Missing/string `order_id` | 422 | `invalid_input` |
| Unsupported view method | 405 | `method_not_allowed`, with `Allow` |
| Handler exception | 500 | `internal_failure` |

The host maps demonstration tokens to Alice with `orders:read` and Bob without
that scope. Replace this dictionary with trusted host verification before
deployment. Callers cannot supply their own granted scopes. The example does
not disable CSRF or configure a production authentication stack; those paths
are simply outside the request-factory evidence.

The native view decodes `request.body` with the standard-library JSON decoder
and rejects non-object bodies. Agnara checks the declared scope before schema
validation, resource acquisition or handler effects. Bob's object with a string
`order_id` therefore yields a policy denial. Credentials and Django objects
never enter invocation metadata or Agnara DI.

## Explicit lifecycle ownership

`build_host()` creates an application-owned view handle. Its `Host.lifespan()`
is an example async context manager, not a Django lifecycle API. Entering it
declares/freezes capabilities, compiles plans, binds the application port and
constructs the live container/runtime on the current event loop:

```python
state = State()
host = build_host(state)
async with host.lifespan():
    status, body = await drive(host)
```

These names belong to the example; import them from its source when reusing
the fixture. The audit singleton is an async generator whose `finally` records
cleanup. Exiting the owner context closes the runtime, closes that resource
and clears the retained handles on the same loop, including exceptional exit.
The audit list is in-memory fixture state, not persistence or transactions.

Await each view call, or own concurrent calls with `asyncio.TaskGroup`. Drain
them, or cancel and await them, before exiting the owner context. Cancellation
propagates as `CancelledError`, rather than becoming a canonical failure or a
successful response. The context manager does not drain arbitrary external
work automatically.

One live runtime/container belongs to one event loop. Do not put it in module
globals, share it across threads/loops, create it in `AppConfig.ready()`, or
nest `asyncio.run()` inside a view. This example supplies no server startup
adapter. A real embedding must explicitly establish matching startup,
invocation, drainage and shutdown ownership. Django documents that async views
under WSGI use one-off loops in its [async support guide](https://docs.djangoproject.com/en/6.1/topics/async/);
this fixture is not a WSGI or synchronous bridge.

## Outcomes and evidence

The host maps canonical forbidden/input/timeout/conflict failures to
403/422/504/409 and uses 500 for remaining outcomes. Responses contain the
canonical code only, never private details or exception diagnostics. This is
the fixture's mapping, not a universal HTTP policy; capabilities with other
interaction outcomes require explicit mapping.

The [tests](../tests/docs/test_django_embedding_example.py) check native view
independence, refusal before application effects, overlapping principal/context
isolation, unique execution identities, propagated cancellation, construction
and resource cleanup on the owning loop, exceptional exit and execution of the
script outside the checkout. Existing [Django fixtures](../tests/integration/django/test_embedding.py)
provide separate bounded evidence for nested calls and explicit idempotency.

No URL configuration, network/server hosting, Django ORM/session integration,
automatic retry, streaming projection or durable execution is introduced.
Consult the [interoperability limits](INTEROPERABILITY.md) before extending
the example to a production host.
