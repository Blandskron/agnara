# Streaming a capability over HTTP

Use `Http.sse` to project an explicitly declared capability stream as
server-sent events. Each successful unit becomes one JSON `message` event;
the terminal event distinguishes completion from a failure after output.

## Run the example

From the repository root with Python 3.14:

```bash
uv sync
uv run python examples/http_sse.py
```

The complete [example](../examples/http_sse.py) uses only governed public
imports and needs no server or external service. It drives the compiled ASGI
application with an in-memory peer and prints:

```text
completed: status=200 units=2 outcome=completed closed=1
denied: status=403 units=0 outcome=forbidden closed=0
invalid_input: status=400 units=0 outcome=invalid_input closed=0
first_failure: status=500 units=0 outcome=internal_failure closed=1
late_failure: status=200 units=1 outcome=interrupted closed=1
disconnect: status=200 units=1 outcome=disconnected closed=1
```

`closed` counts invocation-provider teardown. Zero on the denied and invalid
paths means the resource was never opened. It does not mean a resource leaked.

## Declare and compose

The `rows` capability is an async generator with `streaming=True` and an
explicit `output=dict[str, int]`. The runtime validates every yielded unit
against that output contract; its return annotation alone would not declare
the contract. The `count` input has an explicit query binding:

```python
from agnara_http import Binding, BindingSource, Http

http = Http("public")
http.sse("/rows", rows, Binding("count", BindingSource.QUERY), max_event_bytes=1024)
asgi = http.compile(app.compile(), dependencies=dependencies, request_timeout=2)
```

This is a composition excerpt from the example. `app`, `rows` and
`dependencies` are explicitly defined there. The invocation-scoped async
generator provider opens `ReportSession` and closes it in `finally`.
The handler receives that domain resource by type, with no HTTP request object.

The application compiles once before serving. The example owns ASGI startup,
the request and shutdown on the same event loop; a task group joins its
lifespan task. Request and demonstration timeouts bound execution. A real ASGI
server owns these messages and must keep lifespan enabled and drain requests
before shutdown.

## Read success and failure

For the two-unit success, the wire body is:

```text
data: {"line":0}

data: {"line":1}

event: agnara.terminal
data: {"outcome":"completed","units":2}

```

The response uses `text/event-stream; charset=utf-8` and `cache-control:
no-store`. The response starts only after the first unit can be delivered.
An empty stream still returns `200` and a `completed` terminal with zero units.

The deliberately failing producer uses a synthetic diagnostic to demonstrate
redaction. If it raises before the first unit, the caller receives an ordinary
`500` RFC 9457 problem with `internal_failure`. If it raises after one unit,
HTTP has already started with `200`; the single `agnara.terminal` event instead
carries `outcome: interrupted`, `units: 1` and the redacted problem. Neither
response contains the diagnostic. The client must inspect the terminal outcome
even when the HTTP status was successful.

The producer closes before the invocation provider on success and both failure
paths. Output delivery does not transfer resource ownership to the caller.

## Authorization and invalid input

The shipped HTTP capability boundary invokes as the anonymous principal. This
example does not authenticate a caller or map headers into authority. Its
`protected` capability requires `reports:read`, so the scope policy returns
`403` before constructing `ReportSession` or entering the protected handler.

A non-integer `count` query produces `400 invalid_input` before resource and
handler work. Neither case starts an SSE response or emits a terminal event.
If an authenticated application needs to invoke capabilities through a host,
use the explicit [embedding contract](INTEROPERABILITY.md); this guide adds no
HTTP authentication bridge. Authorization remains independent of discovery.

## Disconnect and limits

The in-memory peer sends `http.disconnect` after receiving the first data
event. The producer then waits for demand; the adapter's owned watcher cancels
it, closes its generator and dependency, and joins its work before returning.
There is no terminal event to a disconnected peer. A connection close without
a terminal must not be interpreted as completed delivery.

The example collects a bounded response for inspection. That collector is not
a network client: a real client must parse SSE incrementally across arbitrary
byte chunks. The adapter itself pulls one unit per completed send without a
prefetch queue. The regression tests also verify that no task survives a case.

This projection has these limits (ADR 0085):

- GET only, with path, query, header or cookie bindings; no request body.
- One encoded event is bounded by `max_event_bytes`; larger units fail instead
  of being truncated.
- SSE routes accept no OpenAPI publication metadata and are absent from the
  generated OpenAPI document.
- No replay, heartbeat, `id`, `retry` or `Last-Event-ID` semantics. A reconnect
  starts a fresh invocation with policy evaluated again.
- Server, proxy and outer middleware own buffering, compression and CORS.

See the [HTTP composition guide](HTTP_COMPOSITION.md) for the complete public
surface and ADRs 0084–0086 for stream ownership, SSE and output validation.
